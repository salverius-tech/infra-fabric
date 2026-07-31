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
    def test_delivery_requires_explicit_consumer_contract(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.technitium.root_password": "SENTINEL"})
        delivered = secret_delivery.deliver(
            provider,
            path="secrets.bootstrap.technitium.root_password",
            consumer="ansible-bootstrap",
        )
        self.assertEqual(delivered.environment_name, "TF_VAR_container_root_password")
        self.assertEqual(delivered.value, "SENTINEL")

    def test_service_delivery_is_scoped_to_selected_services(self) -> None:
        provider = FakeProvider(
            {
                "secrets.bootstrap.technitium.root_password": "ROOT",
                **{requirement.path: f"VALUE_{requirement.environment_name}" for requirement in secret_delivery.SERVICE_REQUIREMENTS if requirement.service == "forgejo"},
            }
        )
        environment = secret_delivery.deliver_services_environment(provider, ["forgejo"])
        self.assertEqual(environment["TF_VAR_container_root_password"], "ROOT")
        self.assertEqual(environment["FORGEJO_SECRET_KEY"], "VALUE_FORGEJO_SECRET_KEY")
        self.assertNotIn("HERMES_CONTROL_API_TOKEN", environment)

    def test_service_delivery_requires_every_selected_contract_secret(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.technitium.root_password": "ROOT"})
        with self.assertRaises(secret_delivery.SecretDeliveryError):
            secret_delivery.deliver_services_environment(provider, ["forgejo"])

    def test_all_contract_secrets_forbid_state_exposure(self) -> None:
        self.assertTrue(secret_delivery.ALL_REQUIREMENTS)
        self.assertTrue(all(requirement.state_exposure == "forbidden" for requirement in secret_delivery.ALL_REQUIREMENTS))

    def test_delivery_rejects_wrong_consumer(self) -> None:
        provider = FakeProvider({"secrets.bootstrap.technitium.root_password": "SENTINEL"})
        with self.assertRaises(secret_delivery.SecretDeliveryError):
            secret_delivery.deliver(
                provider,
                path="secrets.bootstrap.technitium.root_password",
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
        provider = FakeProvider({"secrets.bootstrap.technitium.root_password": "SENTINEL"})
        environment = secret_delivery.deliver_environment(provider, consumer="ansible-bootstrap")
        self.assertEqual(environment, {"TF_VAR_container_root_password": "SENTINEL"})
        self.assertEqual(
            secret_delivery.redact_environment(environment, set(environment)),
            {"TF_VAR_container_root_password": "<redacted>"},
        )


if __name__ == "__main__":
    unittest.main()
