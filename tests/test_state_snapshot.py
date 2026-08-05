from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("state_snapshot", ROOT / "scripts" / "state-snapshot.py")
assert SPEC and SPEC.loader
STATE_SNAPSHOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATE_SNAPSHOT)


def state_bytes(serial: int) -> bytes:
    return (json.dumps({"version": 4, "serial": serial, "resources": []}, sort_keys=True) + "\n").encode()


class StateSnapshotTests(unittest.TestCase):
    def test_absent_state_is_skipped_without_creating_backup_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backup_dir = root / "state-backups"
            self.assertIsNone(STATE_SNAPSHOT.create_snapshot(root / "terraform.tfstate", backup_dir))
            self.assertFalse(backup_dir.exists())

    def test_malformed_state_is_rejected_before_backup_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            state.write_text("not-state\n", encoding="utf-8")
            backup_dir = root / "state-backups"
            with self.assertRaisesRegex(STATE_SNAPSHOT.StateSnapshotError, "document"):
                STATE_SNAPSHOT.create_snapshot(state, backup_dir)
            self.assertFalse(backup_dir.exists())

    def test_snapshot_is_private_complete_and_checksum_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            state.write_bytes(state_bytes(1))
            snapshot = STATE_SNAPSHOT.create_snapshot(state, root / "state-backups")
            assert snapshot is not None

            manifest = STATE_SNAPSHOT.verify_snapshot(snapshot)
            self.assertEqual(manifest["source_name"], "terraform.tfstate")
            self.assertEqual(manifest["size_bytes"], state.stat().st_size)
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o700)
            self.assertEqual((snapshot / "terraform.tfstate").stat().st_mode & 0o777, 0o600)
            self.assertEqual((snapshot / "manifest.json").stat().st_mode & 0o777, 0o600)
            self.assertNotIn("synthetic", json.dumps(manifest))

    def test_snapshot_tampering_fails_integrity_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            state.write_bytes(state_bytes(1))
            snapshot = STATE_SNAPSHOT.create_snapshot(state, root / "state-backups")
            assert snapshot is not None
            (snapshot / "terraform.tfstate").write_text("changed\n", encoding="utf-8")
            os.chmod(snapshot / "terraform.tfstate", 0o600)
            with self.assertRaisesRegex(STATE_SNAPSHOT.StateSnapshotError, "integrity"):
                STATE_SNAPSHOT.verify_snapshot(snapshot)

    def test_retention_keeps_only_the_newest_complete_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            backup_dir = root / "state-backups"
            for sequence in range(4):
                state.write_bytes(state_bytes(sequence))
                STATE_SNAPSHOT.create_snapshot(state, backup_dir, retain=2)
            snapshots = sorted(path for path in backup_dir.iterdir() if path.name.startswith("snapshot-"))
            self.assertEqual(len(snapshots), 2)
            for snapshot in snapshots:
                STATE_SNAPSHOT.verify_snapshot(snapshot)

    def test_restore_requires_acknowledgement_and_revalidates_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            original = state_bytes(1)
            state.write_bytes(original)
            snapshot = STATE_SNAPSHOT.create_snapshot(state, root / "state-backups")
            assert snapshot is not None
            state.write_text("newer-state\n", encoding="utf-8")

            with self.assertRaisesRegex(STATE_SNAPSHOT.StateSnapshotError, "acknowledgement"):
                STATE_SNAPSHOT.restore_snapshot(snapshot, state)
            STATE_SNAPSHOT.restore_snapshot(snapshot, state, replace_existing=True)
            self.assertEqual(state.read_bytes(), original)
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)

    def test_restore_cli_rejects_concurrent_site_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            state.write_bytes(state_bytes(1))
            snapshot = STATE_SNAPSHOT.create_snapshot(state, root / "state-backups")
            assert snapshot is not None
            state.write_bytes(state_bytes(2))
            lock = root / ".infra-fabric.lock"
            with STATE_SNAPSHOT.acquire_site_lock(lock):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "state-snapshot.py"),
                        "restore",
                        "--snapshot",
                        str(snapshot),
                        "--state",
                        str(state),
                        "--replace-existing",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
            self.assertEqual(result.returncode, 2)
            self.assertIn("another operation", result.stderr)
            self.assertEqual(state.read_bytes(), state_bytes(2))

    def test_apply_reverifies_and_snapshots_immediately_before_tofu(self) -> None:
        source = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        snapshot_call = "python scripts/state-snapshot.py create"
        apply_command = "apply_command=(tofu -chdir=infra/opentofu apply"
        self.assertIn("verify_saved_plan\n" + snapshot_call, source)
        self.assertLess(source.index(snapshot_call), source.index(apply_command))
        self.assertIn("Diagnostic only: mutation was authorized", source)


if __name__ == "__main__":
    unittest.main()
