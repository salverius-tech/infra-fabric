"""Sensitive Ansible role inputs must be hidden during argument validation."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE_SECRET_FIELDS = {
    "caddy_proxy": {"caddy_cloudflare_api_token"},
    "forgejo": {
        "caddy_cloudflare_api_token",
        "forgejo_bootstrap_admin_password",
        "forgejo_bootstrap_owner_password",
        "forgejo_internal_token",
        "forgejo_lfs_jwt_secret",
        "forgejo_oauth2_jwt_secret",
        "forgejo_postgres_password",
        "forgejo_secret_key",
    },
    "forgejo_runner": {"forgejo_runner_registration_secret"},
    "hermes": {
        "caddy_cloudflare_api_token",
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
    "onramp_host": {"caddy_cloudflare_api_token"},
    "searxng_onramp": {"searxng_secret_key"},
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

    def test_service_playbooks_wire_catalog_environment_to_sensitive_role_inputs(self) -> None:
        bindings = {
            "forgejo-runner.yml": {
                "FORGEJO_RUNNER_REGISTRATION_SECRET": "forgejo_runner_registration_secret",
            },
            "tailscale-client.yml": {"TS_AUTHKEY": "tailscale_client_auth_key"},
            "searxng-onramp.yml": {"SEARXNG_SECRET_KEY": "searxng_secret_key"},
            "infisical-onramp.yml": {
                "INFISICAL_AUTH_SECRET": "infisical_auth_secret",
                "INFISICAL_ENCRYPTION_KEY": "infisical_encryption_key",
                "INFISICAL_POSTGRES_PASSWORD": "infisical_postgres_password",
            },
        }
        for playbook, expected in bindings.items():
            document = yaml.safe_load(
                (ROOT / "infra/ansible/playbooks" / playbook).read_text(encoding="utf-8")
            )
            variables = document[-1]["vars"]
            for environment_name, variable_name in expected.items():
                self.assertIn(variable_name, variables, f"{playbook}.{variable_name}")
                self.assertIn(environment_name, variables[variable_name])


if __name__ == "__main__":
    unittest.main()
