"""Typed interface coverage for reusable security-sensitive Ansible roles."""

from pathlib import Path
from typing import Any
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "infra/ansible/roles"


class SecurityRoleArgumentSpecsTests(unittest.TestCase):
    def role_contract(self, role: str) -> tuple[dict[str, Any], dict[str, Any]]:
        defaults = yaml.safe_load((ROLES / role / "defaults/main.yml").read_text(encoding="utf-8"))
        specs = yaml.safe_load((ROLES / role / "meta/argument_specs.yml").read_text(encoding="utf-8"))
        return defaults, specs["argument_specs"]["main"]["options"]

    def test_defaults_are_fully_declared_for_both_security_roles(self) -> None:
        for role in ("host_identity", "root_credentials"):
            defaults, options = self.role_contract(role)
            self.assertEqual(set(defaults), set(options), role)

    def test_host_identity_types_and_secret_handling_are_explicit(self) -> None:
        _, options = self.role_contract("host_identity")
        for key in ("host_identity_provisioning_keys", "host_identity_operator_keys"):
            self.assertEqual(options[key]["type"], "list")
            self.assertEqual(options[key]["elements"], "str")
        password = options["host_identity_operator_password"]
        self.assertTrue(password["required"])
        self.assertIn("out of logs", password["description"])
        tasks = (ROLES / "host_identity/tasks/main.yml").read_text(encoding="utf-8")
        self.assertIn("Set the protected operator sudo password", tasks)
        self.assertIn("no_log: true", tasks)

    def test_root_credentials_exposes_only_the_non_secret_salt(self) -> None:
        _, options = self.role_contract("root_credentials")
        self.assertEqual(set(options), {"root_credentials_root_password_hash_salt"})
        self.assertIn("non-secret", options["root_credentials_root_password_hash_salt"]["description"])
        tasks = (ROLES / "root_credentials/tasks/main.yml").read_text(encoding="utf-8")
        self.assertIn("lookup('env', 'INFRA_BOOTSTRAP_ROOT_PASSWORD')", tasks)
        self.assertIn("no_log: true", tasks)


if __name__ == "__main__":
    unittest.main()
