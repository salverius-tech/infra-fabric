from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report-plan-equivalence.py"


def tofu_plan(*, vmid: int, sensitive: str = "placeholder") -> dict[str, object]:
    return {
        "resource_changes": [{
            "address": "resource.example",
            "change": {
                "actions": ["update"],
                "before": {"vmid": vmid - 1},
                "after": {"vmid": vmid, "password": sensitive},
                "after_sensitive": {"password": True},
            },
        }]
    }


class ReportPlanEquivalenceTests(unittest.TestCase):
    def run_report(self, before: dict[str, object], after: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="hermes-plan-report-") as directory:
            before_path = Path(directory) / "before.json"
            after_path = Path(directory) / "after.json"
            before_path.write_text(json.dumps(before), encoding="utf-8")
            after_path.write_text(json.dumps(after), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(before_path), str(after_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_equivalent_report_is_redacted_and_successful(self) -> None:
        result = self.run_report(tofu_plan(vmid=101), tofu_plan(vmid=101, sensitive="different-secret"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"differences": [], "equivalent": True})
        self.assertNotIn("different-secret", result.stdout)

    def test_changed_plan_is_redacted_and_nonzero(self) -> None:
        result = self.run_report(tofu_plan(vmid=101), tofu_plan(vmid=102))
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report["equivalent"])
        self.assertEqual(report["differences"], [{"address": "resource.example", "kind": "values_changed"}])
        self.assertNotIn("102", result.stdout)

    def test_invalid_plan_is_error_without_values(self) -> None:
        result = self.run_report({"resource_changes": {}}, tofu_plan(vmid=101))
        self.assertEqual(result.returncode, 2)
        self.assertIn("resource_changes must be a list", result.stdout)


if __name__ == "__main__":
    unittest.main()
