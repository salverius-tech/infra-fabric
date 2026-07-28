from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from plan_equivalence import PlanEquivalenceError, compare_plans


def plan(*resources: dict[str, object], **metadata: object) -> dict[str, object]:
    return {"resources": list(resources), **metadata}


class PlanEquivalenceTests(unittest.TestCase):
    def test_formatting_and_declared_path_metadata_are_ignored(self) -> None:
        before = plan(
            {"address": "service.forgejo", "actions": ["update"], "values": {"vmid": 101}},
            formatting="pretty",
            path_metadata={"source": "/tmp/a"},
        )
        after = plan(
            {"address": "service.forgejo", "actions": ["update"], "values": {"vmid": 101}},
            formatting="compact",
            path_metadata={"source": "/tmp/b"},
        )
        self.assertEqual(compare_plans(before, after), {"equivalent": True, "differences": []})

    def test_resource_address_changes_are_not_equivalent(self) -> None:
        result = compare_plans(
            plan({"address": "service.old", "actions": ["create"], "values": {"vmid": 101}}),
            plan({"address": "service.new", "actions": ["create"], "values": {"vmid": 101}}),
        )
        self.assertFalse(result["equivalent"])
        self.assertEqual({item["kind"] for item in result["differences"]}, {"resource_added", "resource_removed"})

    def test_actions_and_infrastructure_values_are_significant(self) -> None:
        result = compare_plans(
            plan({"address": "service.forgejo", "actions": ["update"], "values": {"runtime": "lxc", "vmid": 101}}),
            plan({"address": "service.forgejo", "actions": ["delete", "create"], "values": {"runtime": "vm", "vmid": 102}}),
        )
        self.assertFalse(result["equivalent"])
        self.assertEqual(
            {item["kind"] for item in result["differences"]},
            {"actions_changed", "values_changed"},
        )

    def test_unknown_and_known_values_are_not_collapsed(self) -> None:
        result = compare_plans(
            plan({"address": "service.forgejo", "actions": ["update"], "values": {"vmid": {"unknown": True}}}),
            plan({"address": "service.forgejo", "actions": ["update"], "values": {"vmid": 101}}),
        )
        self.assertFalse(result["equivalent"])
        self.assertEqual(result["differences"], [{"address": "service.forgejo", "kind": "values_changed"}])

    def test_malformed_resources_fail_closed(self) -> None:
        with self.assertRaises(PlanEquivalenceError):
            compare_plans({"resources": [{"address": "x", "actions": []}, {"address": "x", "actions": []}]}, {"resources": []})


if __name__ == "__main__":
    unittest.main()
