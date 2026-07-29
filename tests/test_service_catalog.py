from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from service_catalog import ServiceCatalogError, load_catalog


class ServiceCatalogTests(unittest.TestCase):
    def write_catalog(self, data: dict) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        with handle:
            json.dump(data, handle)
        path = Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    def test_loads_repository_catalog_and_validates_selection(self) -> None:
        path = Path(__file__).resolve().parents[1] / "infra" / "services.json"
        catalog = load_catalog(path)
        self.assertIn("forgejo", catalog.names)
        catalog.validate_selection({"forgejo", "forgejo_runner"})
        searxng = catalog.get("searxng_onramp")
        self.assertEqual(searxng.raw["release"]["source"], "container")
        self.assertEqual(searxng.raw["release"]["legacy_image_var"], "searxng_container_image")
        self.assertEqual(searxng.raw["release"]["canonical_fields"], ["release.image", "release.digest"])

    def test_required_secret_paths_follow_enabled_services(self) -> None:
        catalog = load_catalog(
            self.write_catalog(
                {
                    "services": {
                        "app": {"dependencies": [], "required_secrets": ["services.app.token"]},
                        "db": {"dependencies": [], "required_secrets": ["shared.database.password"]},
                    }
                }
            )
        )
        self.assertEqual(
            catalog.required_secret_paths({"app", "db"}),
            {"services.app.token", "shared.database.password"},
        )
        services = {
            "app": SimpleNamespace(enabled=True, dependencies=[], state=SimpleNamespace(capable=False)),
            "db": SimpleNamespace(enabled=False, dependencies=[], state=SimpleNamespace(capable=False)),
        }
        self.assertEqual(catalog.required_secret_paths_for_model(services), {"services.app.token"})

    def test_optional_secret_classification_is_typed_and_report_is_redacted(self) -> None:
        catalog = load_catalog(
            self.write_catalog(
                {
                    "services": {
                        "app": {
                            "dependencies": [],
                            "required_secrets": ["services.app.token"],
                            "secret_classifications": {"services.app.token": "runtime"},
                        },
                        "disabled": {"dependencies": [], "required_secrets": ["services.disabled.token"]},
                    }
                }
            )
        )
        self.assertEqual(
            catalog.required_secret_report({"app"}),
            ({"service": "app", "path": "services.app.token", "classification": "runtime", "required": True},),
        )

    def test_invalid_secret_classification_fails_at_load(self) -> None:
        for classifications in ({"services.app.token": "logical"}, {"services.other.token": "runtime"}):
            with self.subTest(classifications=classifications), self.assertRaisesRegex(
                ServiceCatalogError, "secret_classifications"
            ):
                load_catalog(
                    self.write_catalog(
                        {
                            "services": {
                                "app": {
                                    "dependencies": [],
                                    "required_secrets": ["services.app.token"],
                                    "secret_classifications": classifications,
                                }
                            }
                        }
                    )
                )

    def test_invalid_required_secret_path_fails_at_load(self) -> None:
        with self.assertRaisesRegex(ServiceCatalogError, "required_secrets must be logical paths"):
            load_catalog(
                self.write_catalog(
                    {"services": {"app": {"dependencies": [], "required_secrets": ["services..app.token"]}}}
                )
            )

    def test_invalid_required_secret_path_fails_at_load(self) -> None:
        for path in ("services..app.token", "Services.app.token", "services/app/token", "services.app.bad key"):
            with self.subTest(path=path), self.assertRaisesRegex(ServiceCatalogError, "required_secrets must be logical paths"):
                load_catalog(
                    self.write_catalog(
                        {"services": {"app": {"dependencies": [], "required_secrets": [path]}}}
                    )
                )

    def test_secret_classifications_are_validated_and_reported_without_values(self) -> None:
        catalog = load_catalog(
            self.write_catalog(
                {
                    "services": {
                        "app": {
                            "dependencies": [],
                            "required_secrets": ["services.app.token"],
                            "secret_classifications": {"services.app.token": "runtime"},
                        }
                    }
                }
            )
        )
        self.assertEqual(
            catalog.required_secret_report({"app"}),
            ({"service": "app", "path": "services.app.token", "required": True, "classification": "runtime"},),
        )
        for classification in ("secret", "", "RUNTIME"):
            with self.subTest(classification=classification), self.assertRaisesRegex(ServiceCatalogError, "secret_classifications"):
                load_catalog(
                    self.write_catalog(
                        {
                            "services": {
                                "app": {
                                    "dependencies": [],
                                    "required_secrets": ["services.app.token"],
                                    "secret_classifications": {"services.app.token": classification},
                                }
                            }
                        }
                    )
                )

    def test_enabled_service_resource_type_must_match_catalog_replacements(self) -> None:
        catalog = load_catalog(
            self.write_catalog(
                {
                    "services": {
                        "app": {
                            "dependencies": [],
                            "terraform_replace_addresses": {"lxc": ["module.app"]},
                        }
                    }
                }
            )
        )
        service = SimpleNamespace(enabled=True, resource="guest", dependencies=[], state=SimpleNamespace(capable=False))
        resources = SimpleNamespace(
            guests={"guest": SimpleNamespace(type="vm")},
            shared_hosts={},
        )
        with self.assertRaisesRegex(ServiceCatalogError, "resource type"):
            catalog.validate_model_services({"app": service}, resources)

    def test_missing_dependency_fails_closed(self) -> None:
        catalog = load_catalog(
            self.write_catalog(
                {"services": {"app": {"dependencies": ["db"]}, "db": {"dependencies": []}}}
            )
        )
        with self.assertRaisesRegex(ServiceCatalogError, "requires disabled services"):
            catalog.validate_selection({"app"})

    def test_unknown_enabled_service_fails_closed(self) -> None:
        catalog = load_catalog(self.write_catalog({"services": {"app": {"dependencies": []}}}))
        with self.assertRaisesRegex(ServiceCatalogError, "not in catalog"):
            catalog.validate_selection({"missing"})

    def test_unknown_canonical_service_fails_closed_even_when_disabled(self) -> None:
        catalog = load_catalog(self.write_catalog({"services": {"app": {"dependencies": []}}}))
        with self.assertRaisesRegex(ServiceCatalogError, "canonical services are not in catalog"):
            catalog.validate_model_services({"missing": SimpleNamespace(dependencies=[], state=SimpleNamespace(capable=False))})

    def test_canonical_dependency_override_must_match_catalog(self) -> None:
        catalog = load_catalog(
            self.write_catalog(
                {"services": {"app": {"dependencies": ["db"]}, "db": {"dependencies": []}}}
            )
        )
        service = SimpleNamespace(dependencies=["other"], state=SimpleNamespace(capable=False))
        with self.assertRaisesRegex(ServiceCatalogError, "declares dependencies"):
            catalog.validate_model_services({"app": service, "db": SimpleNamespace(dependencies=[], state=SimpleNamespace(capable=False))})

    def test_dependency_cycle_fails_at_load(self) -> None:
        with self.assertRaisesRegex(ServiceCatalogError, "dependency cycle"):
            load_catalog(
                self.write_catalog(
                    {
                        "services": {
                            "a": {"dependencies": ["b"]},
                            "b": {"dependencies": ["a"]},
                        }
                    }
                )
            )

    def test_unknown_dependency_fails_at_load(self) -> None:
        with self.assertRaisesRegex(ServiceCatalogError, "unknown service"):
            load_catalog(self.write_catalog({"services": {"app": {"dependencies": ["missing"]}}}))
    def test_real_hermes_catalog_conditional_secret_matrix(self) -> None:
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
        def service(control: bool, dashboard: bool) -> SimpleNamespace:
            return SimpleNamespace(
                enabled=True,
                dependencies=[],
                state=SimpleNamespace(capable=False),
                configuration={"control": {"enabled": control}, "dashboard": {"enabled": dashboard}},
            )
        api = {"services.hermes.secrets.control_api_token", "services.hermes.secrets.control_bridge_token"}
        dashboard = {"services.hermes.secrets.dashboard_basic_auth_password_hash", "services.hermes.secrets.dashboard_basic_auth_secret"}
        self.assertEqual(catalog.required_secret_paths_for_model({"hermes": service(False, False)}), frozenset())
        self.assertEqual(catalog.required_secret_paths_for_model({"hermes": service(True, False)}), api)
        self.assertEqual(catalog.required_secret_paths_for_model({"hermes": service(False, True)}), dashboard)
        self.assertEqual(catalog.required_secret_paths_for_model({"hermes": service(True, True)}), api | dashboard)
        report = catalog.required_secret_report_for_model({"hermes": service(True, True)})
        self.assertEqual({entry["path"] for entry in report}, api | dashboard)
        self.assertNotIn("value", repr(report))
        with self.assertRaisesRegex(ServiceCatalogError, "required_secret_report_for_model"):
            catalog.required_secret_report({"hermes"})

        catalog = load_catalog(
            self.write_catalog(
                {
                    "services": {
                        "hermes": {
                            "dependencies": [],
                            "required_secrets": [
                                "services.hermes.secrets.control_api_token",
                                "services.hermes.secrets.dashboard_secret",
                            ],
                            "secret_classifications": {
                                "services.hermes.secrets.control_api_token": "runtime",
                                "services.hermes.secrets.dashboard_secret": "runtime",
                            },
                            "conditional_required_secrets": {
                                "configuration.control.enabled": ["services.hermes.secrets.control_api_token"],
                                "configuration.dashboard.enabled": ["services.hermes.secrets.dashboard_secret"],
                            },
                        }
                    }
                }
            )
        )
        base = {"enabled": True, "dependencies": [], "state": SimpleNamespace(capable=False)}
        disabled = SimpleNamespace(**base, configuration={"control": {"enabled": False}, "dashboard": {"enabled": False}})
        self.assertEqual(catalog.required_secret_paths_for_model({"hermes": disabled}), frozenset())
        enabled = SimpleNamespace(**base, configuration={"control": {"enabled": True}, "dashboard": {"enabled": True}})
        self.assertEqual(
            catalog.required_secret_paths_for_model({"hermes": enabled}),
            {"services.hermes.secrets.control_api_token", "services.hermes.secrets.dashboard_secret"},
        )
        report = catalog.required_secret_report_for_model({"hermes": enabled})
        self.assertEqual({entry["path"] for entry in report}, {"services.hermes.secrets.control_api_token", "services.hermes.secrets.dashboard_secret"})
        self.assertNotIn("value", repr(report))


if __name__ == "__main__":
    unittest.main()
