from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "guest-mount-feature-vars.py"
spec = importlib.util.spec_from_file_location("guest_mount_feature_vars", SCRIPT)
assert spec and spec.loader
guest_mount_feature_vars = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guest_mount_feature_vars
spec.loader.exec_module(guest_mount_feature_vars)


class GuestMountFeatureVarsTests(unittest.TestCase):
    def test_lxc_guest_nfs_requires_nfs_mount_feature(self) -> None:
        checks = guest_mount_feature_vars.build_feature_checks(
            ["forgejo"],
            {
                "forgejo_container_vmid": 107,
                "service_runtime": {"forgejo": {"type": "lxc"}},
                "service_storage": {
                    "forgejo": {
                        "data": {
                            "type": "guest_nfs",
                            "target": "/var/lib/forgejo",
                        }
                    }
                },
            },
        )

        self.assertEqual(
            checks,
            [
                {
                    "service": "forgejo",
                    "mount": "data",
                    "vmid": 107,
                    "feature": "nfs",
                    "storage_type": "guest_nfs",
                }
            ],
        )

    def test_vm_guest_nfs_does_not_require_lxc_mount_feature(self) -> None:
        checks = guest_mount_feature_vars.build_feature_checks(
            ["forgejo"],
            {
                "forgejo_container_vmid": 107,
                "service_runtime": {"forgejo": {"type": "vm"}},
                "service_storage": {
                    "forgejo": {
                        "data": {
                            "type": "guest_nfs",
                            "target": "/var/lib/forgejo",
                        }
                    }
                },
            },
        )

        self.assertEqual(checks, [])

    def test_main_accepts_canonical_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            projection = Path(temp) / "terraform.auto.tfvars.json"
            projection.write_text(
                json.dumps(
                    {
                        "enabled_services": ["forgejo"],
                        "forgejo_container_vmid": 107,
                        "service_runtime": {"forgejo": {"type": "lxc"}},
                        "service_storage": {
                            "forgejo": {
                                "data": {
                                    "type": "guest_nfs",
                                    "target": "/var/lib/forgejo",
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = guest_mount_feature_vars.main(
                    ["--projection", str(projection)]
                )

        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(output.getvalue())["guest_mount_feature_checks"][0]["feature"],
            "nfs",
        )

    def test_main_rejects_missing_or_malformed_projection_sections(self) -> None:
        for payload in (
            {},
            {"enabled_services": ["forgejo"], "service_runtime": []},
            {"enabled_services": ["forgejo"], "service_storage": []},
        ):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                projection = Path(temp) / "terraform.auto.tfvars.json"
                projection.write_text(json.dumps(payload), encoding="utf-8")
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(
                        guest_mount_feature_vars.main(
                            ["--projection", str(projection)]
                        ),
                        1,
                    )


if __name__ == "__main__":
    unittest.main()
