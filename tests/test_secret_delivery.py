from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "scripts"
for name in ("secret_provider", "secret_delivery"):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
secret_delivery = sys.modules["secret_delivery"]

service_catalog_spec = importlib.util.spec_from_file_location("service_catalog", ROOT / "service_catalog.py")
assert service_catalog_spec and service_catalog_spec.loader
service_catalog = importlib.util.module_from_spec(service_catalog_spec)
sys.modules["service_catalog"] = service_catalog
service_catalog_spec.loader.exec_module(service_catalog)


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

    def test_proxmox_provider_contract_delivers_api_token_only_to_opentofu(self) -> None:
        provider = FakeProvider({secret_delivery.PROXMOX_PROVIDER_PATH: "TOKEN"})
        requirements = secret_delivery.provider_requirements()
        environment = secret_delivery.deliver_environment(
            provider,
            consumer="opentofu-provider",
            requirements=requirements,
        )
        self.assertEqual(environment, {"PROXMOX_VE_API_TOKEN": "TOKEN"})
        with self.assertRaises(secret_delivery.SecretDeliveryError):
            secret_delivery.deliver_environment(
                provider,
                consumer="ansible-bootstrap",
                requirements=requirements,
            )

    def test_provider_contract_rejects_unsupported_provider(self) -> None:
        with self.assertRaisesRegex(secret_delivery.SecretDeliveryError, "unsupported canonical provider"):
            secret_delivery.provider_requirements("unknown")

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
        catalog = service_catalog.load_catalog(ROOT.parents[0] / "infra" / "services.json")
        services = {"forgejo": SimpleNamespace(enabled=True, configuration={})}
        requirements = secret_delivery.requirements_for_model(catalog, services)
        provider = FakeProvider(
            {requirement.path: f"VALUE_{requirement.environment_name}" for requirement in requirements}
        )
        environment = secret_delivery.deliver_services_environment(provider, catalog, services)
        self.assertNotIn("INFRA_BOOTSTRAP_ROOT_PASSWORD", environment)
        self.assertEqual(environment["FORGEJO_SECRET_KEY"], "VALUE_FORGEJO_SECRET_KEY")
        self.assertNotIn("HERMES_CONTROL_API_TOKEN", environment)

    def test_catalog_model_requirements_use_service_owned_paths_and_feature_conditions(self) -> None:
        catalog = service_catalog.load_catalog(ROOT.parents[0] / "infra" / "services.json")
        services = {
            "hermes": SimpleNamespace(
                enabled=True,
                configuration={"control": {"enabled": True}, "dashboard": {"enabled": False}},
            )
        }

        requirements = secret_delivery.requirements_for_model(catalog, services)

        self.assertEqual(
            {requirement.path for requirement in requirements},
            {
                "services.hermes.secrets.control_api_token",
                "services.hermes.secrets.control_bridge_token",
                "secrets.providers.cloudflare.api_token",
            },
        )
        self.assertEqual(
            {requirement.environment_name for requirement in requirements},
            {"HERMES_CONTROL_API_TOKEN", "HERMES_CONTROL_BRIDGE_TOKEN", "CF_DNS_API_TOKEN"},
        )

    def test_service_delivery_requires_every_selected_contract_secret(self) -> None:
        catalog = service_catalog.load_catalog(ROOT.parents[0] / "infra" / "services.json")
        services = {"forgejo": SimpleNamespace(enabled=True, configuration={})}
        provider = FakeProvider({"secrets.bootstrap.root_password": "ROOT"})
        with self.assertRaises(secret_delivery.SecretDeliveryError):
            secret_delivery.deliver_services_environment(provider, catalog, services)

    def test_service_without_runtime_secrets_receives_only_declared_provider_secret(self) -> None:
        catalog = service_catalog.load_catalog(ROOT.parents[0] / "infra" / "services.json")
        services = {"technitium": SimpleNamespace(enabled=True, configuration={})}
        provider = FakeProvider({"secrets.providers.cloudflare.api_token": "CF"})
        environment = secret_delivery.deliver_services_environment(provider, catalog, services)
        self.assertEqual(environment, {"CF_DNS_API_TOKEN": "CF"})
        self.assertNotIn("INFRA_BOOTSTRAP_ROOT_PASSWORD", environment)
        self.assertNotIn("INFRA_OPERATOR_PASSWORD", environment)
        self.assertNotIn("PROXMOX_VE_API_TOKEN", environment)

    def test_infisical_onramp_declares_every_role_secret(self) -> None:
        catalog = service_catalog.load_catalog(ROOT.parents[0] / "infra" / "services.json")
        services = {
            "infisical_onramp": SimpleNamespace(enabled=True, configuration={}),
            "onramp_host": SimpleNamespace(enabled=True, configuration={}),
        }
        requirements = secret_delivery.requirements_for_model(
            catalog,
            services,
            selected_services=["infisical_onramp"],
        )
        self.assertEqual(
            {requirement.environment_name for requirement in requirements},
            {"INFISICAL_AUTH_SECRET", "INFISICAL_ENCRYPTION_KEY", "INFISICAL_POSTGRES_PASSWORD"},
        )

    def test_sssf_delivers_only_the_selected_provider_key(self) -> None:
        catalog = service_catalog.load_catalog(ROOT.parents[0] / "infra" / "services.json")
        services = {
            "sssf": SimpleNamespace(enabled=True, configuration={"provider": "openai"}),
        }
        requirements = secret_delivery.requirements_for_model(catalog, services)
        self.assertEqual(
            {(requirement.path, requirement.environment_name) for requirement in requirements},
            {("services.sssf.secrets.openai_api_key", "OPENAI_API_KEY")},
        )
        environment = secret_delivery.deliver_services_environment(
            FakeProvider({"services.sssf.secrets.openai_api_key": "synthetic"}),
            catalog,
            services,
        )
        self.assertEqual(environment, {"OPENAI_API_KEY": "synthetic"})

    def test_protected_environment_is_removed_before_service_delivery(self) -> None:
        catalog = service_catalog.load_catalog(ROOT.parents[0] / "infra" / "services.json")
        inherited = {
            "SAFE_FLAG": "1",
            "PROXMOX_VE_API_TOKEN": "provider",
            "INFRA_BOOTSTRAP_ROOT_PASSWORD": "root",
            "INFRA_OPERATOR_PASSWORD": "operator",
            "FORGEJO_SECRET_KEY": "forgejo",
            "HERMES_CONTROL_API_TOKEN": "hermes",
        }
        self.assertEqual(
            secret_delivery.without_protected_environment(inherited, catalog),
            {"SAFE_FLAG": "1"},
        )

    def test_model_contract_secrets_forbid_state_exposure(self) -> None:
        catalog = service_catalog.load_catalog(ROOT.parents[0] / "infra" / "services.json")
        services = {"forgejo": SimpleNamespace(enabled=True, configuration={})}
        requirements = secret_delivery.requirements_for_model(catalog, services)
        self.assertTrue(requirements)
        self.assertTrue(all(requirement.state_exposure == "forbidden" for requirement in requirements))

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
