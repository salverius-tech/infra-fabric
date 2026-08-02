from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
for name in ("secret_provider", "secret_delivery"):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
secret_delivery = sys.modules["secret_delivery"]


class FakeProvider:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def resolve(self, logical_path: str) -> str:
        try:
            return self.values[logical_path]
        except KeyError as error:
            raise ValueError("missing") from error


class SecretDeliveryTests(unittest.TestCase):
    def test_root_password_inherits_site_default(self) -> None:
        self.assertEqual(
            secret_delivery.root_password_secret_path("technitium"),
            "secrets.bootstrap.root_password",
        )

    def test_root_password_override_is_host_specific(self) -> None:
        self.assertEqual(
            secret_delivery.root_password_secret_path(
                "forgejo",
                host_overrides={"forgejo": "secrets.bootstrap.hosts.forgejo.root_password"},
            ),
            "secrets.bootstrap.hosts.forgejo.root_password",
        )
        requirements = secret_delivery.root_password_requirements(
            ("technitium", "forgejo"),
            host_overrides={"forgejo": "secrets.bootstrap.hosts.forgejo.root_password"},
        )
        self.assertEqual(
            {requirement.path for requirement in requirements},
            {
                "secrets.bootstrap.root_password",
                "secrets.bootstrap.hosts.forgejo.root_password",
            },
        )

    def test_root_password_override_wins_for_one_resource(self) -> None:
        overrides = {"forgejo": "secrets.bootstrap.hosts.forgejo.root_password"}
        self.assertEqual(
            secret_delivery.root_password_secret_path("forgejo", host_overrides=overrides),
            "secrets.bootstrap.hosts.forgejo.root_password",
        )
        self.assertEqual(
            secret_delivery.root_password_secret_path("hermes", host_overrides=overrides),
            "secrets.bootstrap.root_password",
        )

    def test_root_password_requirements_deduplicate_inherited_secret(self) -> None:
        requirements = secret_delivery.root_password_requirements(
            ["technitium", "hermes", "forgejo"],
            host_overrides={"forgejo": "secrets.bootstrap.hosts.forgejo.root_password"},
        )
        self.assertEqual(
            {requirement.path for requirement in requirements},
            {
                "secrets.bootstrap.root_password",
                "secrets.bootstrap.hosts.forgejo.root_password",
            },
        )

    def test_root_password_requirements_can_be_delivered_to_host_identity(self) -> None:
        requirements = secret_delivery.root_password_requirements(
            ["forgejo"],
            consumer="ansible-host-identity",
        )
        self.assertEqual(requirements[0].consumers, frozenset({"ansible-host-identity"}))

    def test_delivery_requires_explicit_consumer_contract(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.root_password": "SENTINEL"})
        delivered = secret_delivery.deliver(
            provider,
            path="secrets.bootstrap.root_password",
            consumer="ansible-bootstrap",
        )
        self.assertEqual(delivered.environment_name, "INFRA_BOOTSTRAP_ROOT_PASSWORD")
        self.assertEqual(delivered.value, "SENTINEL")

    def test_delivery_rejects_multiline_environment_values(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.root_password": "line1\nline2"})
        with self.assertRaisesRegex(secret_delivery.SecretDeliveryError, "multiline"):
            secret_delivery.deliver(
                provider,
                path="secrets.bootstrap.root_password",
                consumer="ansible-bootstrap",
            )

    def test_delivery_rejects_invalid_environment_names(self) -> None:
        requirement = secret_delivery.SecretRequirement(
            "secrets.bootstrap.root_password",
            "bootstrap",
            frozenset({"ansible-bootstrap"}),
            "not-an-environment",
        )
        with self.assertRaisesRegex(secret_delivery.SecretDeliveryError, "environment name"):
            secret_delivery.deliver(
                FakeProvider({"secrets.bootstrap.root_password": "ROOT"}),
                path=requirement.path,
                consumer="ansible-bootstrap",
                requirements=(requirement,),
            )

    def test_service_delivery_is_scoped_to_selected_services(self) -> None:
        provider = FakeProvider(
            {
                "secrets.bootstrap.root_password": "ROOT",
                **{requirement.path: f"VALUE_{requirement.environment_name}" for requirement in secret_delivery.SERVICE_REQUIREMENTS if requirement.service == "forgejo"},
            }
        )
        environment = secret_delivery.deliver_services_environment(provider, ["forgejo"])
        self.assertEqual(environment["INFRA_BOOTSTRAP_ROOT_PASSWORD"], "ROOT")
        self.assertEqual(environment["FORGEJO_SECRET_KEY"], "VALUE_FORGEJO_SECRET_KEY")
        self.assertNotIn("HERMES_CONTROL_API_TOKEN", environment)

    def test_service_delivery_requires_every_selected_contract_secret(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.root_password": "ROOT"})
        with self.assertRaises(secret_delivery.SecretDeliveryError):
            secret_delivery.deliver_services_environment(provider, ["forgejo"])

    def test_service_without_runtime_secrets_keeps_bootstrap_only(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.root_password": "ROOT"})
        environment = secret_delivery.deliver_services_environment(provider, ["technitium"])
        self.assertEqual(environment, {"INFRA_BOOTSTRAP_ROOT_PASSWORD": "ROOT"})

    def test_all_contract_secrets_forbid_state_exposure(self) -> None:
        self.assertTrue(secret_delivery.ALL_REQUIREMENTS)
        self.assertTrue(all(requirement.state_exposure == "forbidden" for requirement in secret_delivery.ALL_REQUIREMENTS))

    def test_delivery_rejects_wrong_consumer(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.root_password": "SENTINEL"})
        with self.assertRaises(secret_delivery.SecretDeliveryError):
            secret_delivery.deliver(
                provider,
                path="secrets.bootstrap.root_password",
                consumer="opentofu",
            )

    def test_delivery_rejects_uncontracted_path(self) -> None:
        provider = FakeProvider({"secrets.runtime.example.token": "SENTINEL"})
        with self.assertRaises(secret_delivery.SecretDeliveryError):
            secret_delivery.deliver(
                provider,
                path="secrets.runtime.example.token",
                consumer="ansible-bootstrap",
            )

    def test_environment_delivery_is_value_bearing_only_in_memory(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.root_password": "SENTINEL"})
        environment = secret_delivery.deliver_environment(provider, consumer="ansible-bootstrap")
        self.assertEqual(environment, {"INFRA_BOOTSTRAP_ROOT_PASSWORD": "SENTINEL"})
        self.assertEqual(
            secret_delivery.redact_environment(environment, set(environment)),
            {"INFRA_BOOTSTRAP_ROOT_PASSWORD": "<redacted>"},
        )

    def test_environment_delivery_rejects_unknown_consumer(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.root_password": "SENTINEL"})
        with self.assertRaisesRegex(secret_delivery.SecretDeliveryError, "consumer has no approved secret contract"):
            secret_delivery.deliver_environment(provider, consumer="unknown-consumer")


if __name__ == "__main__":
    unittest.main()
