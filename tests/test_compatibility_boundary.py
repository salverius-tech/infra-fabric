from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CompatibilityBoundaryTests(unittest.TestCase):
    def run_gate(self, values_dir: Path, *, allow_legacy: bool = False) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({"VALUES_DIR": str(values_dir), "VALUES_SITE": "dev"})
        if allow_legacy:
            env["INFRA_ALLOW_LEGACY_COMPATIBILITY"] = "true"
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
        self.assertIn("INFRA_ALLOW_LEGACY_COMPATIBILITY=true", result.stderr)

    def test_legacy_compatibility_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_gate(Path(directory), allow_legacy=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("legacy compatibility explicitly enabled", result.stderr)


if __name__ == "__main__":
    unittest.main()
