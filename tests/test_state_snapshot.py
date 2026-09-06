from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "state_snapshot", ROOT / "scripts" / "state-snapshot.py"
)
assert SPEC and SPEC.loader
STATE_SNAPSHOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATE_SNAPSHOT)


def state_bytes(serial: int) -> bytes:
    return (
        json.dumps({"version": 4, "serial": serial, "resources": []}, sort_keys=True)
        + "\n"
    ).encode()


class StateSnapshotTests(unittest.TestCase):
    def test_absent_state_is_skipped_without_creating_backup_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backup_dir = root / "state-backups"
            self.assertIsNone(
                STATE_SNAPSHOT.create_snapshot(root / "terraform.tfstate", backup_dir)
            )
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
            self.assertEqual(
                (snapshot / "terraform.tfstate").stat().st_mode & 0o777, 0o600
            )
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

    def test_create_keeps_staging_and_publication_on_held_root_after_root_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            state.write_bytes(state_bytes(1))
            backup_dir = root / "state-backups"
            redirected = root / "redirected"
            redirected.mkdir()
            original_copy = STATE_SNAPSHOT.atomic_copy

            def copy_then_swap(*args, **kwargs):
                original_copy(*args, **kwargs)
                backup_dir.rename(root / "state-backups-original")
                backup_dir.symlink_to(redirected, target_is_directory=True)

            with patch.object(
                STATE_SNAPSHOT, "atomic_copy", side_effect=copy_then_swap
            ):
                snapshot = STATE_SNAPSHOT.create_snapshot(state, backup_dir)
            assert snapshot is not None
            self.assertTrue(snapshot.is_dir())
            self.assertFalse(any(redirected.iterdir()))

    def test_retention_keeps_only_the_newest_complete_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            backup_dir = root / "state-backups"
            for sequence in range(4):
                state.write_bytes(state_bytes(sequence))
                STATE_SNAPSHOT.create_snapshot(state, backup_dir, retain=2)
            snapshots = sorted(
                path
                for path in backup_dir.iterdir()
                if path.name.startswith("snapshot-")
            )
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

            with self.assertRaisesRegex(
                STATE_SNAPSHOT.StateSnapshotError, "acknowledgement"
            ):
                STATE_SNAPSHOT.restore_snapshot(snapshot, state)
            STATE_SNAPSHOT.restore_snapshot(snapshot, state, replace_existing=True)
            self.assertEqual(state.read_bytes(), original)
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)

    def test_restore_preserves_destination_created_after_absence_check(self) -> None:
        """Caller-level non-replace publication must not race an exists() check."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            state.write_bytes(state_bytes(1))
            snapshot = STATE_SNAPSHOT.create_snapshot(state, root / "state-backups")
            assert snapshot is not None
            state.unlink()
            original_copy = STATE_SNAPSHOT.atomic_copy

            def create_then_copy(*args, **kwargs):
                state.write_bytes(b"racer")
                return original_copy(*args, **kwargs)

            with patch.object(
                STATE_SNAPSHOT, "atomic_copy", side_effect=create_then_copy
            ), self.assertRaisesRegex(
                STATE_SNAPSHOT.StateSnapshotError, "acknowledgement"
            ):
                STATE_SNAPSHOT.restore_snapshot(snapshot, state)
            self.assertEqual(state.read_bytes(), b"racer")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_restore_uses_held_snapshot_entry_after_root_swap_in_both_modes(
        self,
    ) -> None:
        for replace_existing in (False, True):
            with self.subTest(
                replace_existing=replace_existing
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                state = root / "terraform.tfstate"
                expected = state_bytes(1)
                state.write_bytes(expected)
                snapshot = STATE_SNAPSHOT.create_snapshot(state, root / "backups")
                assert snapshot is not None
                state.write_bytes(state_bytes(9))
                alternate = STATE_SNAPSHOT.create_snapshot(
                    state, root / "alternate-backups"
                )
                assert alternate is not None
                destination = root / "recovered" / "terraform.tfstate"
                if replace_existing:
                    destination.parent.mkdir()
                    destination.write_bytes(b"existing")
                original_copy = STATE_SNAPSHOT.atomic_copy

                def swap_then_copy(
                    held,
                    *args,
                    bound_root=root,
                    bound_snapshot=snapshot,
                    bound_alternate=alternate,
                    bound_copy=original_copy,
                    **kwargs,
                ):
                    moved = bound_root / "snapshot-original"
                    bound_snapshot.rename(moved)
                    bound_snapshot.symlink_to(bound_alternate, target_is_directory=True)
                    return bound_copy(held, *args, **kwargs)

                with patch.object(
                    STATE_SNAPSHOT, "atomic_copy", side_effect=swap_then_copy
                ):
                    STATE_SNAPSHOT.restore_snapshot(
                        snapshot, destination, replace_existing=replace_existing
                    )
                self.assertEqual(destination.read_bytes(), expected)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_restore_copies_held_verified_bytes_after_snapshot_path_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "terraform.tfstate"
            expected = state_bytes(1)
            source.write_bytes(expected)
            snapshot = STATE_SNAPSHOT.create_snapshot(source, root / "backups")
            assert snapshot is not None
            destination = root / "recovered" / "terraform.tfstate"
            original_copy = STATE_SNAPSHOT.atomic_copy

            def swap_then_copy(held, *args, **kwargs):
                moved = root / "snapshot-original"
                snapshot.rename(moved)
                replacement = root / "replacement"
                replacement.mkdir()
                (replacement / "terraform.tfstate").write_bytes(state_bytes(9))
                (replacement / "manifest.json").write_bytes(
                    (moved / "manifest.json").read_bytes()
                )
                snapshot.symlink_to(replacement, target_is_directory=True)
                return original_copy(held, *args, **kwargs)

            with patch.object(
                STATE_SNAPSHOT, "atomic_copy", side_effect=swap_then_copy
            ):
                STATE_SNAPSHOT.restore_snapshot(snapshot, destination)
            self.assertEqual(destination.read_bytes(), expected)

    def test_create_rejects_in_place_state_mutation_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            state.write_bytes(state_bytes(1))
            original_copy = STATE_SNAPSHOT.atomic_copy

            original_metadata = state.stat()
            original_identity = (
                original_metadata.st_dev,
                original_metadata.st_ino,
                original_metadata.st_size,
                original_metadata.st_mtime_ns,
            )

            def mutate_then_copy(source, *args, **kwargs):
                state.write_bytes(state_bytes(2))
                os.utime(
                    state,
                    ns=(original_metadata.st_atime_ns, original_metadata.st_mtime_ns),
                )
                mutated = state.stat()
                self.assertEqual(
                    (
                        mutated.st_dev,
                        mutated.st_ino,
                        mutated.st_size,
                        mutated.st_mtime_ns,
                    ),
                    original_identity,
                )
                return original_copy(source, *args, **kwargs)

            with patch.object(
                STATE_SNAPSHOT, "atomic_copy", side_effect=mutate_then_copy
            ), self.assertRaisesRegex(STATE_SNAPSHOT.StateSnapshotError, "changed"):
                STATE_SNAPSHOT.create_snapshot(state, root / "backups")
            self.assertFalse(
                (root / "backups").exists() and any((root / "backups").iterdir())
            )

    def test_create_uses_held_state_when_same_size_pathname_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "terraform.tfstate"
            expected = state_bytes(1)
            state.write_bytes(expected)
            original_copy = STATE_SNAPSHOT.atomic_copy

            def replace_then_copy(held, *args, **kwargs):
                replacement = root / "replacement-state"
                replacement.write_bytes(state_bytes(9))
                self.assertEqual(replacement.stat().st_size, state.stat().st_size)
                replacement.replace(state)
                return original_copy(held, *args, **kwargs)

            with patch.object(
                STATE_SNAPSHOT, "atomic_copy", side_effect=replace_then_copy
            ):
                snapshot = STATE_SNAPSHOT.create_snapshot(state, root / "backups")
            assert snapshot is not None
            self.assertEqual((snapshot / "terraform.tfstate").read_bytes(), expected)

    def test_restore_rejects_held_source_mutation_after_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "terraform.tfstate"
            source.write_bytes(state_bytes(1))
            snapshot = STATE_SNAPSHOT.create_snapshot(source, root / "backups")
            assert snapshot is not None
            destination = root / "recovered" / "terraform.tfstate"
            destination.parent.mkdir()
            destination.write_bytes(b"existing")
            original_copy = STATE_SNAPSHOT.atomic_copy
            snapshot_state = snapshot / "terraform.tfstate"

            def mutate_then_copy(held, *args, **kwargs):
                metadata = snapshot_state.stat()
                snapshot_state.write_bytes(state_bytes(2))
                os.utime(
                    snapshot_state,
                    ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
                )
                return original_copy(held, *args, **kwargs)

            with patch.object(
                STATE_SNAPSHOT, "atomic_copy", side_effect=mutate_then_copy
            ), self.assertRaisesRegex(STATE_SNAPSHOT.StateSnapshotError, "changed"):
                STATE_SNAPSHOT.restore_snapshot(
                    snapshot, destination, replace_existing=True
                )
            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertFalse(list(destination.parent.glob(".terraform.tfstate.*")))

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
        self.assertIn("python scripts/execution-snapshot.py verify --snapshot", source)
        self.assertLess(source.index(snapshot_call), source.index(apply_command))
        self.assertIn("Diagnostic only: mutation was authorized", source)

    def test_lifecycle_state_snapshot_root_override_preserves_the_default_and_container_boundary(
        self,
    ) -> None:
        apply_source = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        teardown_source = (ROOT / "scripts" / "teardown-infra.sh").read_text(
            encoding="utf-8"
        )
        wrapper_source = (ROOT / "scripts" / "run-infra.sh").read_text(encoding="utf-8")
        default = '"${INFRA_STATE_SNAPSHOT_ROOT:-${INFRA_VALUES_DIR}/state-backups}"'
        self.assertIn(default, apply_source)
        self.assertIn(default, teardown_source)
        self.assertIn('--backup-dir "${state_snapshot_root}"', apply_source)
        self.assertIn('--backup-dir "${state_snapshot_root}"', teardown_source)
        self.assertIn("must be an absolute private host path", wrapper_source)
        self.assertIn(
            "INFRA_STATE_SNAPSHOT_ROOT=/run/infra-fabric/state-backups", wrapper_source
        )


if __name__ == "__main__":
    unittest.main()
