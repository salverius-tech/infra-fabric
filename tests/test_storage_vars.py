from __future__ import annotations

import importlib.util
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

    def test_builds_legacy_forgejo_bind_mount_vars(self) -> None:
        tfvars = {
            "forgejo_data_dataset": "tank/forgejo",
            "forgejo_data_host_path": "/tank/forgejo",
            "forgejo_data_host_uid": 100000,
            "forgejo_data_host_gid": 100000,
        }

        mounts = storage_vars.build_storage_mounts(["forgejo"], tfvars)

        self.assertEqual(mounts[0]["source"], "/tank/forgejo")
        self.assertEqual(mounts[0]["target"], "/var/lib/forgejo")
        self.assertEqual(mounts[0]["host_prepare"]["type"], "zfs_dataset")
        self.assertEqual(mounts[0]["host_prepare"]["dataset"], "tank/forgejo")

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
            settings_path = root / "settings.json"
            tfvars_path = root / "terraform.tfvars"
            settings_path.write_text('{"services":["forgejo"]}\n', encoding="utf-8")
            tfvars_path.write_text(
                "service_storage = {\n"
                "  forgejo = {\n"
                "    data = {\n"
                '      type = "bind"\n'
                '      source = "/srv/homelab/forgejo"\n'
                '      target = "/var/lib/forgejo"\n'
                "    }\n"
                "  }\n"
                "}\n",
                encoding="utf-8",
            )

            import contextlib
            import io

            output: list[str] = []
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main(["--settings", str(settings_path), "--tfvars", str(tfvars_path)])

            self.assertEqual(rc, 0)
            output.append(buffer.getvalue())
            payload = json.loads(output[0])
            self.assertEqual(payload["storage_bind_mounts"][0]["source"], "/srv/homelab/forgejo")
            self.assertEqual(payload["storage_bind_mounts"][0]["host_prepare"]["type"], "directory")

    def test_main_filters_to_requested_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings_path = root / "settings.json"
            tfvars_path = root / "terraform.tfvars"
            settings_path.write_text('{"services":["forgejo","hermes"]}\n', encoding="utf-8")
            tfvars_path.write_text(
                "service_storage = {\n"
                "  forgejo = { data = { type = \"bind\", source = \"/srv/forgejo\", target = \"/var/lib/forgejo\" } }\n"
                "  hermes = { data = { type = \"bind\", source = \"/srv/hermes\", target = \"/var/lib/hermes\" } }\n"
                "}\n",
                encoding="utf-8",
            )

            import contextlib
            import io

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main([
                    "--settings",
                    str(settings_path),
                    "--tfvars",
                    str(tfvars_path),
                    "--service",
                    "hermes",
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual([mount["name"] for mount in payload["storage_bind_mounts"]], ["hermes"])

    def test_main_outputs_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings_path = root / "settings.json"
            tfvars_path = root / "terraform.tfvars"
            settings_path.write_text('{"services":["technitium"]}\n', encoding="utf-8")
            tfvars_path.write_text("", encoding="utf-8")

            import contextlib
            import io

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main(["--settings", str(settings_path), "--tfvars", str(tfvars_path), "--summary"])

            self.assertEqual(rc, 0)
            self.assertIn("Storage prep summary:", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
