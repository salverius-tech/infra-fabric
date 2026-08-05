"""Sensitive Ansible role inputs must be hidden during argument validation."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE_SECRET_FIELDS = {
    "forgejo_runner": {"forgejo_runner_registration_secret"},
    "hermes": {
        "hermes_dashboard_basic_auth_password_hash",
        "hermes_dashboard_basic_auth_secret",
        "hermes_control_api_token",
        "hermes_control_bridge_token",
    },
    "hermes_control": {"hermes_control_api_token", "hermes_control_bridge_token"},
    "host_identity": {"host_identity_operator_password"},
    "infisical": {
        "infisical_encryption_key",
        "infisical_auth_secret",
        "infisical_postgres_password",
        "caddy_cloudflare_api_token",
    },
    "infisical_onramp": {
        "infisical_encryption_key",
        "infisical_auth_secret",
        "infisical_postgres_password",
    },
    "tailscale_client": {"tailscale_client_auth_key"},
}


class SensitiveArgumentSpecsTests(unittest.TestCase):
    def test_known_secret_fields_are_no_log(self) -> None:
        for role, fields in ROLE_SECRET_FIELDS.items():
            path = ROOT / "infra/ansible/roles" / role / "meta/argument_specs.yml"
            options = yaml.safe_load(path.read_text(encoding="utf-8"))["argument_specs"]["main"]["options"]
            for field in fields:
                self.assertIn(field, options, f"{role}.{field}")
                self.assertTrue(options[field].get("no_log"), f"{role}.{field}")


if __name__ == "__main__":
    unittest.main()
