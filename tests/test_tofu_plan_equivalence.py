from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from plan_equivalence import compare_plans
from tofu_plan_equivalence import TofuPlanError, normalize_tofu_plan


class TofuPlanEquivalenceTests(unittest.TestCase):
    def test_normalizes_resource_changes(self) -> None:
        normalized = normalize_tofu_plan(
            {
                "format_version": "1.2",
                "resource_changes": [
                    {
                        "address": "proxmox_virtual_environment_container.technitium",
                        "change": {
                            "actions": ["update"],
                            "before": {"vmid": 100},
                            "after": {"vmid": 101, "hostname": "dns.example.internal"},
                            "after_unknown": {"hostname": False},
                            "after_sensitive": {"hostname": False},
                        },
                        "provider_name": "registry.opentofu.org/bpg/proxmox",
                    }
                ],
            }
        )
        self.assertEqual(normalized["schema_version"], 1)
        self.assertEqual(normalized["resources"], [{
            "address": "proxmox_virtual_environment_container.technitium",
            "actions": ["update"],
            "values": {"vmid": 101, "hostname": "dns.example.internal"},
        }])

    def test_preserves_unknown_and_sensitive_markers(self) -> None:
        normalized = normalize_tofu_plan(
            {
                "resource_changes": [{
                    "address": "resource.example",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"id": None, "password": "redacted"},
                        "after_unknown": {"id": True},
                        "after_sensitive": {"password": True},
                    },
                }]
            }
        )
        self.assertEqual(
            normalized["resources"][0]["values"],
            {"id": {"unknown": True}, "password": {"sensitive": True}},
        )

    def test_normalized_output_compares_with_provider_neutral_contract(self) -> None:
        document = {
            "resource_changes": [{
                "address": "resource.example",
                "change": {"actions": ["no-op"], "before": {"vmid": 101}, "after": {"vmid": 101}},
            }]
        }
        normalized = normalize_tofu_plan(document)
        self.assertEqual(compare_plans(normalized, normalized), {"equivalent": True, "differences": []})

    def test_invalid_resource_changes_fail_closed(self) -> None:
        with self.assertRaises(TofuPlanError):
            normalize_tofu_plan({"resource_changes": {}})
        with self.assertRaises(TofuPlanError):
            normalize_tofu_plan({"resource_changes": [{"address": "x", "change": {"actions": []}}]})
        with self.assertRaises(TofuPlanError):
            normalize_tofu_plan({"resource_changes": [{"change": {"actions": ["create"]}}]})


if __name__ == "__main__":
    unittest.main()
