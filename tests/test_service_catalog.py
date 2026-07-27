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

    def test_invalid_required_secret_path_fails_at_load(self) -> None:
        with self.assertRaisesRegex(ServiceCatalogError, "required_secrets must be logical paths"):
            load_catalog(
                self.write_catalog(
                    {"services": {"app": {"dependencies": [], "required_secrets": ["services..app.token"]}}}
                )
            )

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


if __name__ == "__main__":
    unittest.main()
