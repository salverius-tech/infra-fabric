#!/usr/bin/env python3
"""Create, verify, and restore private snapshots of the Hermes audit journal."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

SCRIPT = Path(__file__).with_name("hermes-operator.py")
_spec = importlib.util.spec_from_file_location("hermes_operator", SCRIPT)
assert _spec and _spec.loader
_operator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_operator)

SCHEMA_VERSION = 1
JOURNAL_NAME = "hermes-operator-audit.jsonl"
MANIFEST_NAME = "manifest.json"


class AuditSnapshotError(RuntimeError):
    """Raised when an audit snapshot is unavailable or unsafe."""


def _regular_file(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise AuditSnapshotError(f"{label} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise AuditSnapshotError(f"{label} must be a regular non-symlink file")
    return metadata


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_directory(path: Path) -> None:
    if path.is_symlink():
        raise AuditSnapshotError("audit snapshot directory is unsafe")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise AuditSnapshotError("audit snapshot directory is unsafe")
    path.chmod(0o700)


def _journal_metadata(journal: Path) -> tuple[int, str, int]:
    metadata = _regular_file(journal, "audit journal")
    if metadata.st_mode & 0o077:
        raise AuditSnapshotError("audit journal permissions are not private")
    try:
        head_hash, record_count = _operator.read_audit_chain(journal)
    except _operator.OperatorError as error:
        raise AuditSnapshotError(str(error)) from error
    return record_count, head_hash, metadata.st_size


def verify_snapshot(snapshot: Path) -> dict[str, object]:
    """Verify snapshot permissions, checksum, and audit-chain continuity."""
    if snapshot.is_symlink() or not snapshot.is_dir():
        raise AuditSnapshotError("audit snapshot is not a safe directory")
    if snapshot.stat().st_mode & 0o077:
        raise AuditSnapshotError("audit snapshot directory permissions are not private")
    journal = snapshot / JOURNAL_NAME
    manifest_path = snapshot / MANIFEST_NAME
    journal_metadata = _regular_file(journal, "snapshot journal")
    _regular_file(manifest_path, "snapshot manifest")
    if journal_metadata.st_mode & 0o077 or manifest_path.stat().st_mode & 0o077:
        raise AuditSnapshotError("audit snapshot file permissions are not private")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditSnapshotError("audit snapshot manifest is invalid") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise AuditSnapshotError("audit snapshot manifest schema is invalid")
    if manifest.get("size_bytes") != journal_metadata.st_size or _sha256(journal) != manifest.get("sha256"):
        raise AuditSnapshotError("audit snapshot integrity check failed")
    record_count, head_hash, _ = _journal_metadata(journal)
    if manifest.get("record_count") != record_count or manifest.get("head_hash") != head_hash:
        raise AuditSnapshotError("audit snapshot chain metadata does not match")
    return manifest


def create_snapshot(journal: Path, backup_dir: Path) -> Path:
    """Atomically create one verified private audit snapshot."""
    record_count, head_hash, size_bytes = _journal_metadata(journal)
    _private_directory(backup_dir)
    temporary = Path(tempfile.mkdtemp(prefix=".audit-snapshot-", dir=backup_dir))
    temporary.chmod(0o700)
    try:
        staged_journal = temporary / JOURNAL_NAME
        shutil.copyfile(journal, staged_journal)
        staged_journal.chmod(0o600)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_name": journal.name,
            "size_bytes": size_bytes,
            "sha256": _sha256(journal),
            "record_count": record_count,
            "head_hash": head_hash,
        }
        staged_manifest = temporary / MANIFEST_NAME
        staged_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        staged_manifest.chmod(0o600)
        final = backup_dir / f"snapshot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        os.replace(temporary, final)
        verify_snapshot(final)
        return final
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def restore_snapshot(snapshot: Path, journal: Path, *, replace_existing: bool = False) -> None:
    """Restore a verified snapshot atomically, requiring explicit replacement."""
    verify_snapshot(snapshot)
    if journal.exists() and not replace_existing:
        raise AuditSnapshotError("audit journal already exists; explicit replacement acknowledgement is required")
    _private_directory(journal.parent)
    temporary = Path(tempfile.mkstemp(prefix=f".{journal.name}.", dir=journal.parent)[1])
    try:
        temporary.chmod(0o600)
        shutil.copyfile(snapshot / JOURNAL_NAME, temporary)
        temporary.chmod(0o600)
        os.replace(temporary, journal)
        _journal_metadata(journal)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--journal", type=Path, required=True)
    create.add_argument("--backup-dir", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--snapshot", type=Path, required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--snapshot", type=Path, required=True)
    restore.add_argument("--journal", type=Path, required=True)
    restore.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            snapshot = create_snapshot(args.journal, args.backup_dir)
            print(f"audit snapshot created: {snapshot.name}")
        elif args.command == "verify":
            manifest = verify_snapshot(args.snapshot)
            print(f"audit snapshot verified: records={manifest['record_count']}")
        else:
            restore_snapshot(args.snapshot, args.journal, replace_existing=args.replace_existing)
            print("audit journal snapshot restored")
    except (AuditSnapshotError, OSError) as error:
        print(f"audit snapshot failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
