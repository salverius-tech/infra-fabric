"""Canonical service selection remains the sole resource enablement authority."""

from copy import deepcopy
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOFU_PLUGIN_CACHE = os.environ.get("TF_PLUGIN_CACHE_DIR")
TOFU_RUNTIME_AVAILABLE = bool(
    shutil.which("tofu")
    and TOFU_PLUGIN_CACHE
    and any(Path(TOFU_PLUGIN_CACHE).rglob("terraform-provider-proxmox*"))
)
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.canonical_projections import render_ansible_inventory, render_opentofu_variables
from scripts.canonical_values import load_site
from scripts.service_catalog import load_catalog


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "infra/services.json"
SERVICES_TF = ROOT / "infra/opentofu/services.tf"
TAILSCALE_TF = ROOT / "infra/opentofu/tailscale.tf"
PLAN_SCRIPT = ROOT / "scripts/plan-infra.sh"
VARIABLES_TF = ROOT / "infra/opentofu/variables.tf"
ONRAMP_CHECKS_TF = ROOT / "infra/opentofu/onramp-host-checks.tf"


class CanonicalServiceAuthorityTests(unittest.TestCase):
    @staticmethod
    def tofu_console(expression: str, *variables: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "tofu",
                "-chdir=infra/opentofu",
                "console",
                "-var-file=../../scaffold/terraform.tfvars",
                *variables,
            ],
            cwd=ROOT,
            input=f"{expression}\n",
            text=True,
            capture_output=True,
            check=False,
        )

    def test_tailscale_selection_projects_to_tofu_and_inventory_without_legacy_gate(self) -> None:
        data = yaml.safe_load((ROOT / "scaffold/sites/dev/site.yaml").read_text(encoding="utf-8"))
        resource = deepcopy(data["resources"]["guests"]["technitium"])
        resource["identity"].update({"vmid": 108, "hostname": "tailscale-client"})
        resource["network"]["address"] = "192.0.2.108/24"
        data["resources"]["guests"]["tailscale_client"] = resource
        data["services"]["tailscale_client"] = {
            "enabled": True,
            "resource": "tailscale_client",
        }

        with tempfile.TemporaryDirectory() as temporary:
            site_dir = Path(temporary) / "dev"
            site_dir.mkdir()
            site_file = site_dir / "site.yaml"
            site_file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            model = load_site(site_file, expected_site="dev", catalog_path=CATALOG_PATH)

        catalog = load_catalog(CATALOG_PATH)
        tofu = render_opentofu_variables(model, catalog)
        inventory = render_ansible_inventory(model, catalog)
        services_tf = SERVICES_TF.read_text(encoding="utf-8")
        tailscale_tf = TAILSCALE_TF.read_text(encoding="utf-8")

        self.assertIn("tailscale_client", tofu["enabled_services"])
        self.assertIn("tailscale_client", inventory)
        self.assertIn('tailscale_client_enabled = local.service_enabled.tailscale_client', services_tf)
        self.assertNotIn('&& var.tailscale_client_enabled', services_tf)
        self.assertIn("local.tailscale_client_enabled", tailscale_tf)

    def test_retired_opentofu_selection_aliases_fail_closed(self) -> None:
        variables = VARIABLES_TF.read_text(encoding="utf-8")
        services = SERVICES_TF.read_text(encoding="utf-8")
        scaffold = (ROOT / "scaffold/terraform.tfvars").read_text(encoding="utf-8")

        self.assertRegex(variables, r'(?s)variable "forgejo_runtime" \{.*?default\s+=\s+null')
        self.assertRegex(variables, r'(?s)variable "tailscale_client_enabled" \{.*?default\s+=\s+null')
        self.assertIn("var.forgejo_runtime == null", services)
        self.assertIn("var.tailscale_client_enabled == null", services)
        self.assertNotIn("tailscale_client_enabled", scaffold)

    def test_runtime_selection_defaults_and_acceptance_are_catalog_backed(self) -> None:
        catalog = load_catalog(CATALOG_PATH)
        services = SERVICES_TF.read_text(encoding="utf-8")

        self.assertEqual(catalog.get("forgejo").runtime.default_type, "lxc")
        self.assertEqual(catalog.get("onramp_host").runtime.default_type, "vm")
        self.assertEqual(catalog.get("onramp_host").runtime.supported_types, ("vm",))
        self.assertEqual(catalog.get("searxng_onramp").runtime, None)
        self.assertIn("entry.runtime", services)
        self.assertIn("metadata.default_type", services)
        self.assertIn("runtime_service_metadata[service_name].supported_types", services)
        self.assertNotIn("service_runtime_defaults = {", services)

    def test_forgejo_vm_selects_the_checksum_verified_service_image(self) -> None:
        services = SERVICES_TF.read_text(encoding="utf-8")
        main = (ROOT / "infra/opentofu/main.tf").read_text(encoding="utf-8")
        forgejo = (ROOT / "infra/opentofu/forgejo.tf").read_text(encoding="utf-8")

        self.assertIn("local.forgejo_enabled && local.forgejo_runtime_type == \"vm\"", services)
        self.assertRegex(
            main,
            r'(?s)resource "proxmox_download_file" "debian_13_service_vm_image" \{.*?count\s+=\s+local\.service_vm_image_enabled.*?checksum\s+=\s+var\.guest_vm_image_checksum',
        )
        self.assertRegex(
            forgejo,
            r'(?s)module "forgejo_vm" \{.*?count\s+=\s+local\.forgejo_enabled && local\.forgejo_runtime_type == "vm".*?file_id\s+=\s+.*?proxmox_download_file\.debian_13_service_vm_image\[0\]\.id',
        )

    @unittest.skipUnless(TOFU_RUNTIME_AVAILABLE, "OpenTofu runtime plugins are available in the infra tooling container")
    def test_hcl_evaluates_forgejo_vm_as_requiring_the_service_image(self) -> None:
        result = self.tofu_console(
            "local.service_vm_image_enabled",
            '-var=enabled_services=["forgejo"]',
            '-var=service_runtime={forgejo={type="vm"}}',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "true")

    @unittest.skipUnless(TOFU_RUNTIME_AVAILABLE, "OpenTofu runtime plugins are available in the infra tooling container")
    def test_hcl_runtime_defaults_apply_when_service_runtime_is_omitted_or_partial(self) -> None:
        omitted = self.tofu_console("local.forgejo_runtime.type", "-var=service_runtime={}")
        partial = self.tofu_console(
            "local.forgejo_runtime.type",
            '-var=service_runtime={forgejo={cloud_init_user="forgejo"}}',
        )
        for result in (omitted, partial):
            with self.subTest(output=result.stdout):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip().splitlines()[-1], '"lxc"')

    @unittest.skipUnless(TOFU_RUNTIME_AVAILABLE, "OpenTofu runtime plugins are available in the infra tooling container")
    def test_hcl_rejects_unsupported_runtime_choices_and_retired_aliases(self) -> None:
        cases = (
            ('-var=service_runtime={forgejo={type="baremetal"}}', "service_runtime entries must use type lxc or vm."),
            ('-var=service_runtime={onramp_host={type="lxc"}}', "onramp_host is VM-only"),
            ('-var=forgejo_runtime={type="vm"}', "forgejo_runtime is a retired OpenTofu alias"),
            ('-var=tailscale_client_enabled=true', "tailscale_client_enabled is a retired OpenTofu alias"),
        )
        for variable, expected in cases:
            with self.subTest(variable=variable):
                result = subprocess.run(
                    [
                        "tofu",
                        "-chdir=infra/opentofu",
                        "plan",
                        "-refresh=false",
                        "-input=false",
                        "-lock=false",
                        "-var-file=../../scaffold/terraform.tfvars",
                        '-var=enabled_services=[]',
                        variable,
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout + result.stderr)

    def test_retained_stateful_disable_policy_is_projected_to_tofu_precondition(self) -> None:
        data = yaml.safe_load((ROOT / "scaffold/sites/dev/site.yaml").read_text(encoding="utf-8"))
        data["services"]["forgejo"]["enabled"] = False
        with tempfile.TemporaryDirectory() as temporary:
            site_dir = Path(temporary) / "dev"
            site_dir.mkdir()
            site_file = site_dir / "site.yaml"
            site_file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            model = load_site(site_file, expected_site="dev", catalog_path=CATALOG_PATH)

        tofu = render_opentofu_variables(model, load_catalog(CATALOG_PATH))
        services_tf = SERVICES_TF.read_text(encoding="utf-8")
        self.assertNotIn("forgejo", tofu["enabled_services"])
        self.assertEqual(tofu["stateful_service_disable_policies"]["forgejo"], "retain")
        self.assertIn("retained_disabled_services", services_tf)
        self.assertIn("var.stateful_destroy_acknowledged", services_tf)
        plan_script = PLAN_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('INFRA_ALLOW_DESTROY:-0', plan_script)
        self.assertIn('-var="stateful_destroy_acknowledged=${stateful_destroy_acknowledged}"', plan_script)

    def test_conditional_service_root_inputs_are_optional_until_canonical_enablement_requires_them(self) -> None:
        model = load_site(ROOT / "scaffold/sites/dev/site.yaml", catalog_path=CATALOG_PATH)
        projected = render_opentofu_variables(model, load_catalog(CATALOG_PATH))
        variables = VARIABLES_TF.read_text(encoding="utf-8")
        services = SERVICES_TF.read_text(encoding="utf-8")
        onramp_checks = ONRAMP_CHECKS_TF.read_text(encoding="utf-8")

        required_when_enabled = {
            "technitium": {
                "technitium_container_vmid",
                "technitium_container_hostname",
                "technitium_container_ipv4_address",
                "technitium_container_dns_servers",
                "technitium_container_search_domain",
                "technitium_container_bridge",
                "technitium_container_cores",
                "technitium_container_memory_mb",
                "technitium_container_disk_gb",
                "technitium_container_swap_mb",
                "technitium_container_ipv4_gateway",
            },
            "forgejo": {
                "forgejo_container_vmid",
                "forgejo_container_hostname",
                "forgejo_container_ipv4_address",
                "forgejo_container_dns_servers",
                "forgejo_container_search_domain",
                "forgejo_container_bridge",
                "forgejo_container_cores",
                "forgejo_container_memory_mb",
                "forgejo_container_disk_gb",
                "forgejo_container_swap_mb",
                "forgejo_lan_ip",
                "forgejo_server_name",
            },
        }
        for service, names in required_when_enabled.items():
            with self.subTest(service=service):
                self.assertTrue(names <= set(projected))
                self.assertIn(f"{service}_required_root_inputs", services)
                self.assertIn(f"Canonical projections must provide all {service.title()} root inputs", services)
            for name in names:
                block = re.search(rf'variable "{name}" \{{(.*?)^\}}', variables, re.MULTILINE | re.DOTALL)
                self.assertIsNotNone(block, name)
                assert block is not None
                self.assertIn("default     = null", block.group(1), name)

        disabled = model.model_copy(deep=True)
        disabled.services["technitium"].enabled = False
        disabled.services["forgejo"].enabled = False
        disabled_projection = render_opentofu_variables(disabled, load_catalog(CATALOG_PATH))
        self.assertFalse(any(name.startswith("technitium_container_") for name in disabled_projection))
        self.assertFalse(any(name.startswith("forgejo_container_") for name in disabled_projection))

        self.assertIn("local.technitium_enabled ? tostring(var.technitium_container_vmid) : null", onramp_checks)
        self.assertIn("local.forgejo_enabled ? tostring(var.forgejo_container_vmid) : null", onramp_checks)


if __name__ == "__main__":
    unittest.main()
