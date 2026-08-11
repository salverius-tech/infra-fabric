from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "forgejo-actions-monitor.py"
SPEC = importlib.util.spec_from_file_location("forgejo_actions_monitor", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)

from canonical_projections import render_projection_set
from canonical_values import load_site, model_digest
from projection_manifest import build_manifest
from service_catalog import load_catalog


class ActionsMonitorContextTests(unittest.TestCase):
    def make_projection_context(self, temporary: str) -> SimpleNamespace:
        site_file = ROOT / "scaffold" / "sites" / "dev" / "site.yaml"
        catalog_path = ROOT / "infra" / "services.json"
        model = load_site(site_file, expected_site="dev", catalog_path=catalog_path)
        catalog = load_catalog(catalog_path)
        projections = render_projection_set(model, catalog)
        generated = Path(temporary) / "generated"
        generated.mkdir(mode=0o700)
        for name, value in projections.items():
            path = generated / name
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            path.chmod(0o600)
        manifest = build_manifest(
            site="dev",
            schema_version=model.schema_version,
            model_digest=model_digest(model),
            secret_digest=None,
            projections=projections,
            renderer_version="test-renderer",
            source_commit="test-source",
        )
        manifest_path = generated / "manifest.json"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        manifest_path.chmod(0o600)
        return SimpleNamespace(
            canonical_site_path=site_file,
            site="dev",
            generated_path=lambda name: generated / name,
            projection_manifest_path=manifest_path,
        )

    def test_monitor_rejects_unselected_site(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(monitor.MonitorError):
                monitor.main(["status"])

    def test_monitor_rejects_missing_canonical_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            values = Path(temp) / "values" / "sites" / "dev"
            values.mkdir(parents=True)
            (values / "site.yaml").write_text(
                "schema_version: 1\nsite: {}\n", encoding="utf-8"
            )
            with patch.dict(
                os.environ,
                {"VALUES_DIR": str(Path(temp) / "values"), "VALUES_SITE": "dev"},
                clear=True,
            ):
                with self.assertRaises(monitor.MonitorError):
                    monitor.main(["status"])

    def test_monitor_verifies_complete_projection_set_and_handoff_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.make_projection_context(temporary)
            self.assertEqual(
                monitor.verify_canonical_monitor_inputs(context),
                context.generated_path("ansible-inventory.json"),
            )

            handoff = context.generated_path("onramp-handoff.json")
            altered = json.loads(handoff.read_text(encoding="utf-8"))
            altered["metadata"]["canonical_site"] = "other"
            handoff.write_text(json.dumps(altered) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(monitor.MonitorError, "do not match"):
                monitor.verify_canonical_monitor_inputs(context)


if __name__ == "__main__":
    unittest.main()
