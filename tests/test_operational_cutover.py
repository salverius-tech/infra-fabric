from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OperationalCutoverTests(unittest.TestCase):
    def test_operational_scripts_are_valid_bash(self) -> None:
        for name in ("validate-values.sh", "plan-infra.sh", "apply-infra.sh"):
            result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=f"{name}: {result.stderr}")

    def test_forensic_importer_does_not_depend_on_canonical_preflight(self) -> None:
        # Recovery-boundary sentinel: a legacy-only source cannot satisfy canonical
        # site preflight, and no normal lifecycle recipe may depend on this importer.
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        importer = justfile[justfile.index("recover-legacy-values-forensics:"):]
        importer = importer[: importer.index("\n# ")]
        self.assertNotIn("check-values", importer)
        self.assertIn("scripts/migrate-values.py", importer)
        for recipe in ("setup remote=", "validate:", "plan:", "apply:", "teardown-plan:", "teardown-apply"):
            start = justfile.index(recipe)
            end = justfile.find("\n# ", start)
            block = justfile[start:] if end < 0 else justfile[start:end]
            self.assertNotIn("recover-legacy-values-forensics", block)


if __name__ == "__main__":
    unittest.main()
