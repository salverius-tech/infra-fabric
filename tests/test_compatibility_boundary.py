from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CompatibilityBoundaryTests(unittest.TestCase):
    def run_gate(self, values_dir: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({"VALUES_DIR": str(values_dir), "VALUES_SITE": "dev"})
        return subprocess.run(
            ["bash", "-c", "source scripts/site-context.sh; require_canonical_authority"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_canonical_site_is_default_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory) / "sites" / "dev"
            site.mkdir(parents=True)
            (site / "site.yaml").write_text("schema_version: 1\n", encoding="utf-8")
            result = self.run_gate(Path(directory))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_only_workspace_fails_closed_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_gate(Path(directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("just setup", result.stderr)
        self.assertIn("migration or recovery", result.stderr)

    def test_legacy_compatibility_environment_cannot_bypass_canonical_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env.update(
                {
                    "VALUES_DIR": directory,
                    "VALUES_SITE": "dev",
                    "INFRA_ALLOW_LEGACY_COMPATIBILITY": "true",
                }
            )
            result = subprocess.run(
                ["bash", "-c", "source scripts/site-context.sh; require_canonical_authority"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("site.yaml", result.stderr)


if __name__ == "__main__":
    unittest.main()
