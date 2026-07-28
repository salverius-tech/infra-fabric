from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from canonical_projections import render_ansible_inventory, render_ansible_vars
from canonical_values import load_site
from service_catalog import load_catalog


ROOT = Path(__file__).resolve().parents[1]


class CanonicalAnsibleProjectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_site(ROOT / "scaffold/sites/dev/site.yaml", catalog_path=ROOT / "infra/services.json")
        cls.catalog = load_catalog(ROOT / "infra/services.json")

    def test_inventory_has_consistent_catalog_owned_enabled_service_hosts(self) -> None:
        inventory = render_ansible_inventory(self.model, self.catalog)
        hostvars = inventory["_meta"]["hostvars"]
        enabled = {name for name, service in self.model.services.items() if service.enabled}
        self.assertEqual(set(inventory["all"]["children"]), {self.catalog.get(name).inventory["group"] for name in enabled})
        for name in enabled:
            capability = self.catalog.get(name)
            host = capability.inventory["host"]
            group = capability.inventory["group"]
            self.assertIn(host, hostvars)
            self.assertIn(host, inventory[group]["hosts"])
            self.assertEqual(hostvars[host]["canonical_service"], name)
            self.assertEqual(hostvars[host]["canonical_site"], "dev")

    def test_vars_projection_contains_enabled_services_only_and_preserves_ownership(self) -> None:
        projected = render_ansible_vars(self.model, self.catalog)
        enabled = {name for name, service in self.model.services.items() if service.enabled}
        self.assertEqual(set(projected["services"]), enabled)
        self.assertEqual(projected["canonical_site"], "dev")
        for name in enabled:
            service = self.model.services[name]
            self.assertEqual(projected["services"][name]["resource"], service.resource)
            resource = self.model.resources.guests.get(service.resource) or self.model.resources.shared_hosts.get(service.resource)
            self.assertEqual(projected["services"][name]["resource_type"], resource.type)
            self.assertIn("endpoints", projected["services"][name])
            self.assertIn("release", projected["services"][name])

    def test_projection_does_not_emit_sensitive_sentinel(self) -> None:
        inventory = render_ansible_inventory(self.model, self.catalog)
        variables = render_ansible_vars(self.model, self.catalog)
        self.assertNotIn("REPLACE_SECRET", repr((inventory, variables)))


if __name__ == "__main__":
    unittest.main()
