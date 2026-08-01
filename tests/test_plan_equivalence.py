from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from plan_equivalence import PlanEquivalenceError, compare_plans


class PlanEquivalenceTests(unittest.TestCase):
    def plan(self, *, actions: list[str] | None = None) -> dict:
        return {
            "format_version": "1.2",
            "resource_changes": [
                {
                    "address": "proxmox_virtual_environment_vm.hermes",
                    "change": {
                        "actions": actions or ["update"],
                        "before": {"vm_id": 101, "memory": 4096},
                        "after": {"vm_id": 101, "memory": 8192},
                        "after_unknown": {"disk": True},
                        "replace_paths": [],
                        "action_reason": "refresh",
                    },
                }
            ],
            "output_changes": {},
        }

    def test_formatting_and_noop_refreshes_are_ignored(self) -> None:
        before = self.plan()
        after = json.loads(json.dumps(before, sort_keys=True, indent=4))
        after["resource_changes"].append(
            {"address": "proxmox_virtual_environment_vm.dns", "change": {"actions": ["no-op"], "before": {"x": 1}, "after": {"x": 1}}}
        )
        self.assertTrue(compare_plans(before, after)["equivalent"])

    def test_create_destroy_and_replacement_are_reported(self) -> None:
        before = {"resource_changes": []}
        after = self.plan(actions=["delete", "create"])
        result = compare_plans(before, after)
        self.assertFalse(result["equivalent"])
        self.assertEqual(result["differences"][0]["kind"], "new-resource-change")
        self.assertEqual(result["differences"][0]["after"]["actions"], ["delete", "create"])

    def test_material_resource_change_is_reported(self) -> None:
        before = self.plan()
        after = self.plan()
        after["resource_changes"][0]["change"]["after"]["memory"] = 16384
        result = compare_plans(before, after)
        self.assertEqual(result["differences"][0]["kind"], "values_changed")
        self.assertEqual(result["differences"][0]["address"], "proxmox_virtual_environment_vm.hermes")

    def test_output_change_is_reported(self) -> None:
        before = {"resource_changes": [], "output_changes": {"dns_target": {"actions": ["update"], "before": "old", "after": "192.0.2.1"}}}
        after = {"resource_changes": [], "output_changes": {"dns_target": {"actions": ["update"], "before": "old", "after": "192.0.2.2"}}}
        self.assertEqual(compare_plans(before, after)["differences"][0]["kind"], "output-change")

    def test_malformed_plan_fails_closed(self) -> None:
        with self.assertRaises(PlanEquivalenceError):
            compare_plans({"resource_changes": "invalid"}, {"resource_changes": []})

    def test_cli_returns_nonzero_for_non_equivalent_plans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "before.json"
            after = root / "after.json"
            before.write_text(json.dumps({"resource_changes": []}), encoding="utf-8")
            after.write_text(json.dumps(self.plan()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "compare-plans.py"), str(before), str(after)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn('"equivalent": false', result.stdout)


if __name__ == "__main__":
    unittest.main()
