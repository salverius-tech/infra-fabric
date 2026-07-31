from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from plan_equivalence import PlanEquivalenceError, compare_plans


def plan(*resources: dict[str, object], **metadata: object) -> dict[str, object]:
    return {"schema_version": 1, "resources": list(resources), **metadata}


class PlanEquivalenceTests(unittest.TestCase):
    def test_public_formatting_fixture_is_equivalent(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures" / "plan-equivalence"
        with (fixture_dir / "equivalent-before.json").open(encoding="utf-8") as stream:
            before = json.load(stream)
        with (fixture_dir / "equivalent-after.json").open(encoding="utf-8") as stream:
            after = json.load(stream)
        self.assertEqual(compare_plans(before, after), {"equivalent": True, "differences": []})

    def test_public_replacement_fixture_is_not_an_update(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures" / "plan-equivalence"
        with (fixture_dir / "equivalent-before.json").open(encoding="utf-8") as stream:
            before = json.load(stream)
        with (fixture_dir / "replacement.json").open(encoding="utf-8") as stream:
            replacement = json.load(stream)
        result = compare_plans(before, replacement)
        self.assertFalse(result["equivalent"])
        self.assertEqual(result["differences"], [{"address": "service.forgejo", "kind": "actions_changed"}])

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

    def test_refresh_only_read_and_noop_actions_are_equivalent(self) -> None:
        before = plan({"address": "data.remote", "actions": ["read"], "values": {"id": "same"}})
        after = plan({"address": "data.remote", "actions": ["no-op"], "values": {"id": "same"}})
        self.assertEqual(compare_plans(before, after), {"equivalent": True, "differences": []})

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

    def test_replacement_action_shape_is_preserved_and_significant(self) -> None:
        before = plan(
            {"address": "service.forgejo", "actions": ["delete", "create"], "values": {"vmid": 101}}
        )
        after = plan(
            {"address": "service.forgejo", "actions": ["update"], "values": {"vmid": 101}}
        )
        result = compare_plans(before, after)
        self.assertFalse(result["equivalent"])
        self.assertEqual(result["differences"], [{"address": "service.forgejo", "kind": "actions_changed"}])

    def test_invalid_action_or_missing_values_fails_closed(self) -> None:
        with self.assertRaises(PlanEquivalenceError):
            compare_plans(
                plan({"address": "x", "actions": ["replace"], "values": {}}),
                plan({"address": "x", "actions": ["update"], "values": {}}),
            )
        with self.assertRaises(PlanEquivalenceError):
            compare_plans(
                plan({"address": "x", "actions": ["create"]}),
                plan({"address": "x", "actions": ["create"], "values": {}}),
            )

    def test_duplicate_addresses_fail_closed(self) -> None:
        with self.assertRaises(PlanEquivalenceError):
            compare_plans(
                plan(
                    {"address": "x", "actions": ["create"], "values": {}},
                    {"address": "x", "actions": ["create"], "values": {}},
                ),
                plan(),
            )

    def test_schema_version_is_required(self) -> None:
        with self.assertRaises(PlanEquivalenceError):
            compare_plans({"resources": []}, {"schema_version": 1, "resources": []})



if __name__ == "__main__":
    unittest.main()
