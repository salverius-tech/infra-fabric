from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-coverage-floors.py"
spec = importlib.util.spec_from_file_location("check_coverage_floors", SCRIPT)
assert spec is not None and spec.loader is not None
coverage_floors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage_floors)


class CoverageFloorTests(unittest.TestCase):
    def test_accepts_modules_at_or_above_floor(self) -> None:
        report = {
            "files": {
                "scripts/atomic_output.py": {"summary": {"percent_covered": 85.0}}
            }
        }
        policy = {"schema_version": 1, "floors": {"scripts/atomic_output.py": 85}}

        self.assertEqual(coverage_floors.check_floors(report, policy), [])

    def test_rejects_module_below_floor_with_named_failure(self) -> None:
        report = {
            "files": {
                "scripts/atomic_output.py": {"summary": {"percent_covered": 84.9}}
            }
        }
        policy = {"schema_version": 1, "floors": {"scripts/atomic_output.py": 85}}

        self.assertEqual(
            coverage_floors.check_floors(report, policy),
            ["scripts/atomic_output.py: 84.9% is below the 85% floor"],
        )

    def test_rejects_missing_critical_module(self) -> None:
        report = {"files": {}}
        policy = {"schema_version": 1, "floors": {"scripts/site_lock.py": 80}}

        self.assertEqual(
            coverage_floors.check_floors(report, policy),
            ["scripts/site_lock.py: missing from coverage report"],
        )

    def test_rejects_invalid_floor_policy(self) -> None:
        with self.assertRaises(coverage_floors.CoverageFloorError):
            coverage_floors.check_floors({}, {"schema_version": 2, "floors": {}})


if __name__ == "__main__":
    unittest.main()
