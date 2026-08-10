from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OPERATOR = load_module("hermes_operator_for_snapshot", ROOT / "scripts" / "hermes-operator.py")
SNAPSHOT = load_module("hermes_audit_snapshot", ROOT / "scripts" / "hermes-audit-snapshot.py")


class HermesAuditSnapshotTests(unittest.TestCase):
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
            self.assertEqual(manifest["record_count"], 2)
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o700)
            self.assertEqual((snapshot / "hermes-operator-audit.jsonl").stat().st_mode & 0o777, 0o600)
            self.assertEqual((snapshot / "manifest.json").stat().st_mode & 0o777, 0o600)

    def test_tampered_snapshot_fails_checksum_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = SNAPSHOT.create_snapshot(self._journal(root), root / "backups")
            journal = snapshot / "hermes-operator-audit.jsonl"
            journal.write_text(journal.read_text().replace('"ok":true', '"ok":false'), encoding="utf-8")
            journal.chmod(0o600)
            with self.assertRaisesRegex(SNAPSHOT.AuditSnapshotError, "integrity"):
                SNAPSHOT.verify_snapshot(snapshot)

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
            self.assertEqual(SNAPSHOT._operator.read_audit_chain(destination)[1], 2)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def test_restore_rejects_tampered_snapshot_before_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = SNAPSHOT.create_snapshot(self._journal(root), root / "backups")
            manifest = json.loads((snapshot / "manifest.json").read_text())
            manifest["head_hash"] = "0" * 64
            (snapshot / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (snapshot / "manifest.json").chmod(0o600)
            destination = root / "recovered" / "audit.jsonl"
            with self.assertRaisesRegex(SNAPSHOT.AuditSnapshotError, "chain metadata"):
                SNAPSHOT.restore_snapshot(snapshot, destination, replace_existing=True)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
