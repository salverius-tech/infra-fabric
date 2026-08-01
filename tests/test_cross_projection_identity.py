from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from canonical_projections import ProjectionError, verify_cross_projection_identity


class CrossProjectionIdentityTests(unittest.TestCase):
    def projections(self) -> tuple[dict, dict, dict]:
        return (
            {"service_runtime": {"forgejo": {"type": "lxc"}}},
            {
                "_meta": {"hostvars": {"forgejo": {"canonical_service": "forgejo", "canonical_resource": "forgejo"}}},
                "all": {"vars": {"canonical_site": "dev"}},
            },
            {"canonical_site": "dev", "services": {"forgejo": {"resource": "forgejo", "resource_type": "lxc"}}},
        )

    def test_matching_projections_are_verified(self) -> None:
        opentofu, inventory, ansible_vars = self.projections()
        result = verify_cross_projection_identity(
            site="dev", opentofu=opentofu, inventory=inventory, ansible_vars=ansible_vars
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["services"]["forgejo"]["resource"], "forgejo")

    def test_runtime_type_mismatch_is_rejected(self) -> None:
        opentofu, inventory, ansible_vars = self.projections()
        opentofu["service_runtime"]["forgejo"]["type"] = "vm"
        with self.assertRaises(ProjectionError):
            verify_cross_projection_identity(
                site="dev", opentofu=opentofu, inventory=inventory, ansible_vars=ansible_vars
            )

    def test_wrong_site_is_rejected(self) -> None:
        opentofu, inventory, ansible_vars = self.projections()
        ansible_vars["canonical_site"] = "prod"
        with self.assertRaises(ProjectionError):
            verify_cross_projection_identity(
                site="dev", opentofu=opentofu, inventory=inventory, ansible_vars=ansible_vars
            )
    def test_extra_runtime_service_is_rejected(self) -> None:
        opentofu, inventory, ansible_vars = self.projections()
        opentofu["service_runtime"]["technitium"] = {"type": "lxc"}
        with self.assertRaisesRegex(ProjectionError, "service identity sets"):
            verify_cross_projection_identity(
                site="dev", opentofu=opentofu, inventory=inventory, ansible_vars=ansible_vars
            )
    def test_multiple_services_may_share_one_inventory_host(self) -> None:
        opentofu = {"service_runtime": {"onramp_host": {"type": "lxc"}}}
        inventory = {
            "_meta": {
                "hostvars": {
                    "onramp_host_vm": {
                        "canonical_service": "onramp_host",
                        "canonical_services": ["onramp_host", "searxng_onramp"],
                        "canonical_resource": "onramp_host",
                    }
                }
            },
            "all": {"vars": {"canonical_site": "dev"}},
        }
        ansible_vars = {
            "canonical_site": "dev",
            "services": {
                "onramp_host": {"resource": "onramp_host", "resource_type": "lxc"},
                "searxng_onramp": {"resource": "onramp_host", "resource_type": "lxc"},
            },
        }
        self.assertEqual(
            verify_cross_projection_identity(
                site="dev", opentofu=opentofu, inventory=inventory, ansible_vars=ansible_vars
            )["status"],
            "verified",
        )


if __name__ == "__main__":
    unittest.main()
