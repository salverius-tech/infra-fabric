from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(ROOT / "scripts"))
import hermes_audit_chain

OPERATOR = load_module(
    "hermes_operator_for_snapshot", ROOT / "scripts" / "hermes-operator.py"
)
SNAPSHOT = load_module(
    "hermes_audit_snapshot", ROOT / "scripts" / "hermes_audit_snapshot.py"
)


class HermesAuditSnapshotTests(unittest.TestCase):
    def test_snapshot_and_operator_share_importable_audit_chain(self) -> None:
        self.assertIs(OPERATOR.read_audit_chain, hermes_audit_chain.read_audit_chain)
        self.assertNotIn(
            "importlib",
            (ROOT / "scripts" / "hermes-audit-snapshot.py").read_text(encoding="utf-8"),
        )

    def _journal(self, root: Path) -> Path:
        journal = root / "controller" / "audit.jsonl"
        previous = os.environ.get("HERMES_OPERATOR_AUDIT_PATH")
        os.environ["HERMES_OPERATOR_AUDIT_PATH"] = str(journal)
        try:
            OPERATOR.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))
            OPERATOR.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))
        finally:
            if previous is None:
                os.environ.pop("HERMES_OPERATOR_AUDIT_PATH", None)
            else:
                os.environ["HERMES_OPERATOR_AUDIT_PATH"] = previous
        return journal

    def test_create_and_verify_snapshot_is_private_and_chain_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = self._journal(root)
            snapshot = SNAPSHOT.create_snapshot(journal, root / "backups")
            manifest = SNAPSHOT.verify_snapshot(snapshot)
            self.assertEqual(manifest["record_count"], 4)
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                (snapshot / "hermes-operator-audit.jsonl").stat().st_mode & 0o777, 0o600
            )
            self.assertEqual((snapshot / "manifest.json").stat().st_mode & 0o777, 0o600)

    def test_tampered_snapshot_fails_checksum_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = SNAPSHOT.create_snapshot(self._journal(root), root / "backups")
            journal = snapshot / "hermes-operator-audit.jsonl"
            journal.write_text(
                journal.read_text().replace('"ok":true', '"ok":false'), encoding="utf-8"
            )
            journal.chmod(0o600)
            with self.assertRaisesRegex(SNAPSHOT.AuditSnapshotError, "integrity"):
                SNAPSHOT.verify_snapshot(snapshot)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_create_keeps_staging_and_publication_on_held_root_after_root_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = self._journal(root)
            backup_dir = root / "backups"
            redirected = root / "redirected"
            redirected.mkdir()
            original_copy = SNAPSHOT.atomic_copy

            def copy_then_swap(*args, **kwargs):
                original_copy(*args, **kwargs)
                backup_dir.rename(root / "backups-original")
                backup_dir.symlink_to(redirected, target_is_directory=True)

            with patch.object(SNAPSHOT, "atomic_copy", side_effect=copy_then_swap):
                snapshot = SNAPSHOT.create_snapshot(journal, backup_dir)
            self.assertTrue(snapshot.is_dir())
            self.assertFalse(any(redirected.iterdir()))

    def test_restore_requires_explicit_replacement_and_revalidates_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._journal(root)
            snapshot = SNAPSHOT.create_snapshot(source, root / "backups")
            destination = root / "recovered" / "audit.jsonl"
            destination.parent.mkdir()
            destination.write_text("existing\n", encoding="utf-8")
            with self.assertRaisesRegex(SNAPSHOT.AuditSnapshotError, "acknowledgement"):
                SNAPSHOT.restore_snapshot(snapshot, destination)
            SNAPSHOT.restore_snapshot(snapshot, destination, replace_existing=True)
            self.assertEqual(hermes_audit_chain.read_audit_chain(destination)[1], 4)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def test_create_rejects_same_size_journal_replacement_after_chain_validation(
        self,
    ) -> None:
        """The caller must not publish a snapshot from a different journal identity."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = self._journal(root)
            original_reader = SNAPSHOT.read_audit_stream
            swapped = False

            def validate_then_mutate(handle):
                nonlocal swapped
                result = original_reader(handle)
                if not swapped:
                    swapped = True
                    original = journal.read_bytes()
                    journal.write_bytes(original[::-1])  # public-safety: allow-ip
                return result

            with patch.object(
                SNAPSHOT, "read_audit_stream", side_effect=validate_then_mutate
            ), self.assertRaisesRegex(
                SNAPSHOT.AuditSnapshotError, "malformed|unsafe|changed"
            ):
                SNAPSHOT.create_snapshot(journal, root / "backups")
            self.assertFalse(
                (root / "backups").exists() and any((root / "backups").iterdir())
            )

    def test_create_uses_held_journal_when_same_size_pathname_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = self._journal(root)
            expected = journal.read_bytes()
            original_copy = SNAPSHOT.atomic_copy

            def replace_then_copy(held, *args, **kwargs):
                replacement = root / "replacement-journal"
                replacement.write_bytes(expected)
                replacement.replace(journal)
                return original_copy(held, *args, **kwargs)

            with patch.object(SNAPSHOT, "atomic_copy", side_effect=replace_then_copy):
                snapshot = SNAPSHOT.create_snapshot(journal, root / "backups")
            self.assertEqual((snapshot / SNAPSHOT.JOURNAL_NAME).read_bytes(), expected)

    def test_restore_rejects_tampered_snapshot_before_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = SNAPSHOT.create_snapshot(self._journal(root), root / "backups")
            manifest = json.loads((snapshot / "manifest.json").read_text())
            manifest["head_hash"] = "0" * 64
            (snapshot / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (snapshot / "manifest.json").chmod(0o600)
            destination = root / "recovered" / "audit.jsonl"
            with self.assertRaisesRegex(SNAPSHOT.AuditSnapshotError, "chain metadata"):
                SNAPSHOT.restore_snapshot(snapshot, destination, replace_existing=True)
            self.assertFalse(destination.exists())

    def test_restore_preserves_destination_created_after_absence_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = SNAPSHOT.create_snapshot(self._journal(root), root / "backups")
            destination = root / "recovered" / "audit.jsonl"
            original_copy = SNAPSHOT.atomic_copy

            def create_then_copy(*args, **kwargs):
                destination.parent.mkdir(exist_ok=True)
                destination.write_bytes(b"racer")
                return original_copy(*args, **kwargs)

            with patch.object(
                SNAPSHOT, "atomic_copy", side_effect=create_then_copy
            ), self.assertRaisesRegex(SNAPSHOT.AuditSnapshotError, "acknowledgement"):
                SNAPSHOT.restore_snapshot(snapshot, destination)
            self.assertEqual(destination.read_bytes(), b"racer")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_restore_uses_held_snapshot_entry_after_root_swap_in_both_modes(
        self,
    ) -> None:
        for replace_existing in (False, True):
            with self.subTest(
                replace_existing=replace_existing
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = self._journal(root)
                expected = source.read_bytes()
                snapshot = SNAPSHOT.create_snapshot(source, root / "backups")
                alternate = SNAPSHOT.create_snapshot(source, root / "alternate-backups")
                destination = root / "recovered" / "audit.jsonl"
                if replace_existing:
                    destination.parent.mkdir()
                    destination.write_bytes(b"existing")
                original_copy = SNAPSHOT.atomic_copy

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

                with patch.object(SNAPSHOT, "atomic_copy", side_effect=swap_then_copy):
                    SNAPSHOT.restore_snapshot(
                        snapshot, destination, replace_existing=replace_existing
                    )
                self.assertEqual(destination.read_bytes(), expected)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_restore_copies_held_verified_bytes_after_snapshot_path_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = self._journal(root)
            expected = journal.read_bytes()
            snapshot = SNAPSHOT.create_snapshot(journal, root / "backups")
            destination = root / "recovered" / "audit.jsonl"
            original_copy = SNAPSHOT.atomic_copy

            def swap_then_copy(held, *args, **kwargs):
                moved = root / "snapshot-original"
                snapshot.rename(moved)
                replacement = root / "replacement"
                replacement.mkdir()
                (replacement / SNAPSHOT.JOURNAL_NAME).write_bytes(b"replacement\n")
                (replacement / SNAPSHOT.MANIFEST_NAME).write_bytes(
                    (moved / SNAPSHOT.MANIFEST_NAME).read_bytes()
                )
                snapshot.symlink_to(replacement, target_is_directory=True)
                return original_copy(held, *args, **kwargs)

            with patch.object(SNAPSHOT, "atomic_copy", side_effect=swap_then_copy):
                SNAPSHOT.restore_snapshot(snapshot, destination)
            self.assertEqual(destination.read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
