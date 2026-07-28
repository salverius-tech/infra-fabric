from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workspace-preflight.py"
spec = importlib.util.spec_from_file_location("workspace_preflight", SCRIPT)
assert spec and spec.loader
workspace_preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = workspace_preflight
spec.loader.exec_module(workspace_preflight)


class WorkspacePreflightTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        opentofu = root / "infra" / "opentofu"
        opentofu.mkdir(parents=True)
        (opentofu / ".terraform.lock.hcl").write_text("# lock\n", encoding="utf-8")
        values = root / "values"
        values.mkdir()
        (values / "terraform.tfstate").write_text("{}\n", encoding="utf-8")
        (values / "terraform.tfstate.backup").write_text("{}\n", encoding="utf-8")
        return temp, root

    def test_writable_workspace_passes(self) -> None:
        temp, root = self.make_repo()
        with temp:
            self.assertIsNone(workspace_preflight.run(root, require_values=True))

    def test_missing_values_fails_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra" / "opentofu").mkdir(parents=True)
            with self.assertRaises(workspace_preflight.PreflightError):
                workspace_preflight.run(root, require_values=True)

    def test_missing_values_passes_when_not_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra" / "opentofu").mkdir(parents=True)
            self.assertIsNone(workspace_preflight.run(root, require_values=False))

    def test_unexpected_opentofu_artifact_fails(self) -> None:
        temp, root = self.make_repo()
        with temp:
            artifact = root / "infra" / "opentofu" / "errored.tfstate"
            artifact.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(workspace_preflight.PreflightError):
                workspace_preflight.run(root, require_values=True)

    def test_state_lock_fails(self) -> None:
        temp, root = self.make_repo()
        with temp:
            (root / "values" / ".terraform.tfstate.lock.info").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(workspace_preflight.PreflightError):
                workspace_preflight.run(root, require_values=True)
    def test_canonical_site_preflight_renders_and_cleans_temporary_projections(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        shutil.copy2(source_root / "scaffold" / "sites" / "dev" / "site.yaml", site / "site.yaml")
        (root / "infra" / "services.json").write_text(
            (source_root / "infra" / "services.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        with temp, patch.dict(
            os.environ,
            {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"},
            clear=True,
        ):
            self.assertIsNone(workspace_preflight.check_canonical_projection(root))
            self.assertFalse((site / "generated").exists())

    def test_invalid_canonical_site_fails_preflight(self) -> None:
        temp, root = self.make_repo()
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        (site / "site.yaml").write_text("schema_version: 1\n", encoding="utf-8")
        with temp, patch.dict(
            os.environ,
            {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"},
            clear=True,
        ), self.assertRaises(workspace_preflight.PreflightError):
            workspace_preflight.run(root, require_values=True)
    def test_canonical_secret_check_uses_fixed_path_without_decryption(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        shutil.copy2(source_root / "scaffold" / "sites" / "dev" / "site.yaml", site / "site.yaml")
        (site / "secrets.sops.yaml").write_text("encrypted\n", encoding="utf-8")
        with temp, patch.dict(os.environ, {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"}, clear=True), patch.object(
            workspace_preflight,
            "check_sops_age_availability",
            return_value={"provider": "sops-age"},
        ) as check:
            workspace_preflight.check_canonical_secret_availability(root)
        check.assert_called_once_with(
            site / "secrets.sops.yaml",
            environment={"SOPS_AGE_KEY_FILE": "/run/secrets/sops-age-key"},
        )

    def test_canonical_secret_check_sanitizes_provider_failure(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        shutil.copy2(source_root / "scaffold" / "sites" / "dev" / "site.yaml", site / "site.yaml")
        (site / "secrets.sops.yaml").write_text("SECRET_SENTINEL\n", encoding="utf-8")
        with temp, patch.dict(os.environ, {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"}, clear=True), patch.object(
            workspace_preflight,
            "check_sops_age_availability",
            side_effect=workspace_preflight.SecretProviderError("SECRET_SENTINEL"),
        ):
            with self.assertRaisesRegex(workspace_preflight.PreflightError, "canonical secret availability") as context:
                workspace_preflight.check_canonical_secret_availability(root)
        self.assertNotIn("SECRET_SENTINEL", str(context.exception))


if __name__ == "__main__":
    unittest.main()
