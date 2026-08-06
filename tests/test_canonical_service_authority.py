"""Canonical service selection remains the sole resource enablement authority."""

from copy import deepcopy
from pathlib import Path
import re
import tempfile
import unittest

import yaml

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
        self.assertIn('tailscale_client_enabled = contains(local.enabled_services, "tailscale_client")', services_tf)
        self.assertNotIn('&& var.tailscale_client_enabled', services_tf)
        self.assertIn("local.tailscale_client_enabled", tailscale_tf)

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
