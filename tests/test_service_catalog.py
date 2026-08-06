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
        # Most fixtures exercise a different catalog concern. Declare them as
        # runtime-free explicitly so the loader contract stays fail-closed.
        for service in data.get("services", {}).values():
            service.setdefault("runtime_owner", "none")
            service.setdefault("runtime", None)
        return self.write_raw_catalog(data)

    def write_raw_catalog(self, data: dict) -> Path:
        """Write a deliberately unnormalized fixture for loader-boundary tests."""
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
        self.assertIn("sssf", catalog.names)
        catalog.validate_selection({"forgejo", "forgejo_runner"})
        searxng = catalog.get("searxng_onramp")
        self.assertEqual(searxng.raw["release"]["source"], "container")
        self.assertEqual(searxng.raw["release"]["legacy_image_var"], "searxng_container_image")
        self.assertEqual(searxng.raw["release"]["canonical_fields"], ["release.image", "release.digest"])

    def test_runtime_ownership_is_catalog_driven(self) -> None:
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
        self.assertEqual(catalog.get("forgejo").runtime_owner, "guest")
        self.assertEqual(catalog.get("onramp_host").runtime_owner, "shared_host")
        self.assertEqual(catalog.get("searxng_onramp").runtime_owner, "none")
        self.assertEqual(catalog.get("sssf").runtime_owner, "guest")

    def test_runtime_metadata_fails_closed_when_incomplete_or_inconsistent(self) -> None:
        for runtime in (
            {"default_type": "lxc"},
            {"default_type": "lxc", "supported_types": ["vm"]},
            {"default_type": "baremetal", "supported_types": ["baremetal"]},
        ):
            with self.subTest(runtime=runtime), self.assertRaisesRegex(ServiceCatalogError, "runtime"):
                load_catalog(self.write_catalog({"services": {"app": {"dependencies": [], "runtime": runtime}}}))

    def test_runtime_metadata_is_required_for_runtime_owners_and_null_or_omitted_for_none(self) -> None:
        cases = (
            ("guest", {}, "required"),
            ("shared_host", {}, "required"),
            ("none", {"runtime": {"default_type": "vm", "supported_types": ["vm"]}}, "null or omitted"),
        )
        for owner, extra, message in cases:
            with self.subTest(owner=owner, extra=extra), self.assertRaisesRegex(ServiceCatalogError, message):
                load_catalog(
                    self.write_raw_catalog(
                        {"services": {"app": {"dependencies": [], "runtime_owner": owner, **extra}}}
                    )
                )
        self.assertIsNone(
            load_catalog(self.write_raw_catalog({"services": {"app": {"dependencies": [], "runtime_owner": "none"}}})).get("app").runtime
        )

    def test_update_policy_report_is_catalog_derived_and_ordered(self) -> None:
        catalog = load_catalog(
            self.write_catalog(
                {
                    "services": {
                        "manual": {
                            "dependencies": [],
                            "update_policy": {
                                "status": "manual",
                                "detail": "operator reviews the paired pin and checksum",
                            },
                        },
                        "managed": {
                            "dependencies": [],
                            "update_policy": {
                                "status": "managed",
                                "detail": "just update checks the upstream release after the hold",
                            },
                        },
                    }
                }
            )
        )

        self.assertEqual(
            catalog.update_policy_report(),
            (
                {
                    "service": "managed",
                    "status": "managed",
                    "detail": "just update checks the upstream release after the hold",
                },
                {
                    "service": "manual",
                    "status": "manual",
                    "detail": "operator reviews the paired pin and checksum",
                },
            ),
        )

    def test_invalid_update_policy_fails_at_load(self) -> None:
        for policy in ({"status": "managed"}, {"status": "automatic", "detail": "unsupported"}):
            with self.subTest(policy=policy), self.assertRaisesRegex(ServiceCatalogError, "update_policy"):
                load_catalog(self.write_catalog({"services": {"app": {"dependencies": [], "update_policy": policy}}}))

    def test_required_field_report_is_value_free_and_ordered(self) -> None:
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
        forgejo = SimpleNamespace(
            enabled=True,
            resource="forgejo",
            state=SimpleNamespace(capable=True),
            release=SimpleNamespace(version="1.0.0"),
        )
        tailscale = SimpleNamespace(enabled=True, resource="tailscale")
        report = catalog.required_field_report_for_model({"tailscale_client": tailscale, "forgejo": forgejo})
        self.assertEqual(
            report,
            (
                {"service": "forgejo", "field": "resource", "required": True, "present": True},
                {"service": "forgejo", "field": "state.capable", "required": True, "present": True},
                {"service": "forgejo", "field": "release.version", "required": True, "present": True},
                {"service": "tailscale_client", "field": "resource", "required": True, "present": True},
            ),
        )

    def test_resource_owned_required_fields_resolve_against_selected_resource(self) -> None:
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
        service = SimpleNamespace(
            enabled=True,
            resource="onramp-host",
            state=SimpleNamespace(capable=True),
        )
        complete = SimpleNamespace(
            shared_hosts={
                "onramp-host": SimpleNamespace(
                    security=SimpleNamespace(deploy_user="operator", deploy_dir="/srv"),
                    artifacts=SimpleNamespace(
                        caddy_cloudflare=SimpleNamespace(
                            version="2.8.4",
                            checksums={"amd64": "a" * 64, "arm64": "b" * 64},
                        )
                    ),
                )
            },
            guests={},
        )
        report = catalog.required_field_report_for_model({"onramp_host": service}, complete)
        self.assertTrue(all(entry["present"] for entry in report))
        incomplete = SimpleNamespace(
            shared_hosts={"onramp-host": SimpleNamespace(security=SimpleNamespace(deploy_user="operator"))},
            guests={},
        )
        report = catalog.required_field_report_for_model({"onramp_host": service}, incomplete)
        self.assertFalse(report[-1]["present"])

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
        with self.assertRaisesRegex(ServiceCatalogError, "requires disabled services"):
            catalog.validate_model_services(
                {
                    "app": SimpleNamespace(enabled=True, dependencies=["db"], state=SimpleNamespace(capable=False)),
                    "db": SimpleNamespace(enabled=False, dependencies=[], state=SimpleNamespace(capable=False)),
                }
            )

    def test_disabled_services_do_not_emit_required_field_rows(self) -> None:
        catalog = load_catalog(
            self.write_catalog(
                {
                    "services": {
                        "app": {"dependencies": [], "required_fields": ["resource"]},
                        "disabled": {"dependencies": [], "required_fields": ["resource"]},
                    }
                }
            )
        )
        report = catalog.required_field_report_for_model(
            {
                "app": SimpleNamespace(enabled=True, resource="app"),
                "disabled": SimpleNamespace(enabled=False, resource=None),
            }
        )
        self.assertEqual({entry["service"] for entry in report}, {"app"})

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
        cloudflare = {"secrets.providers.cloudflare.api_token"}
        api = {"services.hermes.secrets.control_api_token", "services.hermes.secrets.control_bridge_token"} | cloudflare
        dashboard = {"services.hermes.secrets.dashboard_basic_auth_password_hash", "services.hermes.secrets.dashboard_basic_auth_secret"} | cloudflare
        self.assertEqual(catalog.required_secret_paths_for_model({"hermes": service(False, False)}), cloudflare)
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
