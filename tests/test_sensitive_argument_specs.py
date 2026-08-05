"""Sensitive Ansible role inputs must be hidden during argument validation."""

import json
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
    "sssf": {
        "sssf_fireworks_api_key",
        "sssf_openai_api_key",
        "sssf_openrouter_api_key",
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

    def test_catalog_secret_environment_binds_to_no_log_role_arguments(self) -> None:
        catalog = json.loads((ROOT / "infra/services.json").read_text(encoding="utf-8"))["services"]
        role_options = {
            path.parents[1].name: yaml.safe_load(path.read_text(encoding="utf-8"))["argument_specs"]["main"]["options"]
            for path in (ROOT / "infra/ansible/roles").glob("*/meta/argument_specs.yml")
        }

        for service, capability in catalog.items():
            for logical_path, environment_name in capability.get("secret_environment", {}).items():
                bound_fields: set[str] = set()
                for playbook_name in capability["playbooks"]:
                    playbook_path = ROOT / playbook_name
                    if not playbook_path.is_file():
                        playbook_path = ROOT / "infra/ansible/playbooks" / playbook_name
                    plays = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))
                    for play in plays:
                        for field, value in play.get("vars", {}).items():
                            if isinstance(value, str) and environment_name in value:
                                bound_fields.add(field)

                self.assertTrue(bound_fields, f"{service}.{logical_path} is not wired from {environment_name}")
                for field in bound_fields:
                    matching = [
                        (role, options[field])
                        for role, options in role_options.items()
                        if field in options
                    ]
                    self.assertTrue(matching, f"{service}.{logical_path} binds unknown argument {field}")
                    for role, specification in matching:
                        self.assertTrue(specification.get("no_log"), f"{role}.{field}")


if __name__ == "__main__":
    unittest.main()
