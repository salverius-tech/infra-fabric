from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "storage-vars.py"
spec = importlib.util.spec_from_file_location("storage_vars", SCRIPT)
assert spec and spec.loader
storage_vars = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = storage_vars
spec.loader.exec_module(storage_vars)


class StorageVarsTests(unittest.TestCase):
    def test_builds_enabled_bind_mount_vars(self) -> None:
        tfvars = {
            "service_storage": {
                "forgejo": {
                    "data": {
                        "type": "bind",
                        "source": "/srv/homelab/forgejo",
                        "target": "/var/lib/forgejo",
                        "host_uid": 100000,
                        "host_gid": 100000,
                        "mode": "0750",
                    }
                },
                "infisical": {
                    "data": {
                        "type": "proxmox_volume",
                        "storage_id": "local-lvm",
                        "size_gb": 20,
                        "target": "/var/lib/infisical",
                    }
                },
            }
        }

        mounts = storage_vars.build_storage_mounts(["technitium", "forgejo", "infisical"], tfvars)

        self.assertEqual(
            mounts,
            [
                {
                    "name": "forgejo",
                    "mount": "data",
                    "source": "/srv/homelab/forgejo",
                    "target": "/var/lib/forgejo",
                    "uid": 100000,
                    "gid": 100000,
                    "mode": "0750",
                    "host_prepare": {"type": "directory"},
                }
            ],
        )

    def test_retired_flat_forgejo_storage_is_not_accepted(self) -> None:
        mounts = storage_vars.build_storage_mounts(
            ["forgejo"],
            {
                "forgejo_data_dataset": "tank/forgejo",
                "forgejo_data_host_path": "/tank/forgejo",
            },
        )

        self.assertEqual(mounts, [])

    def test_format_storage_summary_outputs_none(self) -> None:
        self.assertEqual(storage_vars.format_storage_summary([]), "Storage prep summary:\n  none")

    def test_format_storage_summary_outputs_mounts(self) -> None:
        text = storage_vars.format_storage_summary(
            [
                {
                    "name": "forgejo",
                    "mount": "data",
                    "source": "/srv/homelab/forgejo",
                    "target": "/var/lib/forgejo",
                    "uid": 100000,
                    "gid": 100000,
                    "mode": "0750",
                    "host_prepare": {"type": "directory"},
                }
            ]
        )
        self.assertIn("forgejo.data", text)
        self.assertIn("directory source=/srv/homelab/forgejo", text)

    def test_main_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            projection = root / "terraform.auto.tfvars.json"
            projection.write_text(
                json.dumps({
                    "enabled_services": ["forgejo"],
                    "service_storage": {"forgejo": {"data": {
                        "type": "bind",
                        "source": "/srv/homelab/forgejo",
                        "target": "/var/lib/forgejo",
                    }}},
                }),
                encoding="utf-8",
            )

            import contextlib
            import io

            output: list[str] = []
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main(["--projection", str(projection)])

            self.assertEqual(rc, 0)
            output.append(buffer.getvalue())
            payload = json.loads(output[0])
            self.assertEqual(payload["storage_bind_mounts"][0]["source"], "/srv/homelab/forgejo")
            self.assertEqual(payload["storage_bind_mounts"][0]["host_prepare"]["type"], "directory")

    def test_main_accepts_generated_canonical_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            projection = Path(temp) / "terraform.auto.tfvars.json"
            projection.write_text(
                json.dumps(
                    {
                        "enabled_services": ["forgejo"],
                        "service_storage": {
                            "forgejo": {
                                "data": {
                                    "type": "bind",
                                    "source": "/srv/canonical/forgejo",
                                    "target": "/var/lib/forgejo",
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            import contextlib
            import io

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main(["--projection", str(projection)])

            self.assertEqual(rc, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["storage_bind_mounts"][0]["source"], "/srv/canonical/forgejo")

    def test_main_filters_to_requested_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            projection = root / "terraform.auto.tfvars.json"
            projection.write_text(
                json.dumps({
                    "enabled_services": ["forgejo", "hermes"],
                    "service_storage": {
                        "forgejo": {"data": {"type": "bind", "source": "/srv/forgejo", "target": "/var/lib/forgejo"}},
                        "hermes": {"data": {"type": "bind", "source": "/srv/hermes", "target": "/var/lib/hermes"}},
                    },
                }),
                encoding="utf-8",
            )

            import contextlib
            import io

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main([
                    "--projection",
                    str(projection),
                    "--service",
                    "hermes",
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual([mount["name"] for mount in payload["storage_bind_mounts"]], ["hermes"])

    def test_main_outputs_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            projection = root / "terraform.auto.tfvars.json"
            projection.write_text(
                json.dumps(
                    {
                        "enabled_services": ["technitium"],
                        "service_storage": {},
                    }
                ),
                encoding="utf-8",
            )

            import contextlib
            import io

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main(["--projection", str(projection), "--summary"])

            self.assertEqual(rc, 0)
            self.assertIn("Storage prep summary:", buffer.getvalue())

    def test_main_rejects_missing_or_malformed_storage_projection(self) -> None:
        for payload in (
            {},
            {"enabled_services": ["forgejo"], "service_storage": []},
            {
                "enabled_services": ["forgejo"],
                "service_storage": {"forgejo": []},
            },
        ):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                projection = Path(temp) / "terraform.auto.tfvars.json"
                projection.write_text(json.dumps(payload), encoding="utf-8")
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(
                        storage_vars.main(["--projection", str(projection)]),
                        1,
                    )


if __name__ == "__main__":
    unittest.main()
