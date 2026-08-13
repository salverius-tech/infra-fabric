from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SETTINGS = REPO / "scripts" / "settings.py"
settings_spec = importlib.util.spec_from_file_location("settings_script", SETTINGS)
assert settings_spec and settings_spec.loader
settings_script = importlib.util.module_from_spec(settings_spec)
settings_spec.loader.exec_module(settings_script)

SERVICE_REGISTRY = REPO / "infra" / "services.json"
service_registry = json.loads(SERVICE_REGISTRY.read_text(encoding="utf-8"))


class ServiceRegistryParityTests(unittest.TestCase):
    def test_settings_services_are_derived_from_registry(self) -> None:
        expected_services = {
            name: {
                "playbooks": tuple(config["playbooks"]),
                "dependencies": tuple(config["dependencies"]),
                "terraform_addresses": tuple(config.get("terraform_addresses", ())),
                "terraform_replace_addresses": {
                    runtime: tuple(addresses)
                    for runtime, addresses in config.get("terraform_replace_addresses", {}).items()
                },
                "execution_resource": str(config.get("inventory", {}).get("host", "")).strip(),
            }
            for name, config in service_registry["services"].items()
        }
        self.assertEqual(tuple(service_registry["default_services"]), settings_script.DEFAULT_SERVICES)
        self.assertEqual(expected_services, settings_script.SERVICES)
        self.assertEqual(set(service_registry["services"]), settings_script.SERVICE_NAMES)


    def test_opentofu_enabled_services_validation_reads_registry(self) -> None:
        variables = (REPO / "infra" / "opentofu" / "variables.tf").read_text(encoding="utf-8")
        services = (REPO / "infra" / "opentofu" / "services.tf").read_text(encoding="utf-8")
        self.assertIn('jsondecode(file("${path.module}/../services.json"))', services)
        self.assertIn('resource "terraform_data" "enabled_services_validation"', services)
        self.assertIn("invalid_enabled_services", services)
        self.assertNotIn('contains(["technitium"', variables)

    def test_settings_playbook_paths_exist(self) -> None:
        for playbook in settings_script.all_ansible_playbooks():
            self.assertTrue((REPO / playbook).is_file(), playbook)

    def test_direct_service_playbook_target_groups_are_known(self) -> None:
        special = {
            "infra/ansible/playbooks/caddy-proxy.yml": "technitium",
            "infra/ansible/playbooks/technitium-dns.yml": "localhost",
        }
        groups = {
            service: config["inventory"]["group"]
            for service, config in service_registry["services"].items()
        }
        for service, config in settings_script.SERVICES.items():
            for playbook in config["playbooks"]:
                group = special.get(playbook, groups[service])
                self.assertTrue(group == "localhost" or group in groups.values(), playbook)
        self.assertEqual(special["infra/ansible/playbooks/caddy-proxy.yml"], "technitium")


if __name__ == "__main__":
    unittest.main()
