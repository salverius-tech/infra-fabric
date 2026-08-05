"""Canonical service selection remains the sole resource enablement authority."""

from copy import deepcopy
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
