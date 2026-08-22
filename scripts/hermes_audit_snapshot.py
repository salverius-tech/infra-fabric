#!/usr/bin/env python3
"""Create, verify, and restore private snapshots of the Hermes audit journal."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from hermes_audit_chain import AuditChainError, read_audit_stream
    from private_files import (
        PrivateFileError,
        atomic_copy,
        open_private_directory,
        open_regular_child,
        open_regular_file,
        staging_directory,
        stream_sha256_handle,
        write_private_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - direct import in test loaders
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hermes_audit_chain import AuditChainError, read_audit_stream
    from private_files import (
        PrivateFileError,
        atomic_copy,
        open_private_directory,
        open_regular_child,
        open_regular_file,
        staging_directory,
        stream_sha256_handle,
        write_private_manifest,
    )

SCHEMA_VERSION = 1
JOURNAL_NAME = "hermes-operator-audit.jsonl"
MANIFEST_NAME = "manifest.json"


class AuditSnapshotError(RuntimeError):
    """Raised when an audit snapshot is unavailable or unsafe."""


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns


@contextlib.contextmanager
def _verified_snapshot_source(snapshot: Path):
    """Yield the manifest and journal from one held snapshot directory FD."""
    try:
        with open_private_directory(
            snapshot, "audit snapshot"
        ) as directory_fd, open_regular_child(
            directory_fd, JOURNAL_NAME, "snapshot journal"
        ) as journal, open_regular_child(
            directory_fd, MANIFEST_NAME, "snapshot manifest"
        ) as raw_manifest:
            journal_metadata = os.fstat(journal.fileno())
            manifest_metadata = os.fstat(raw_manifest.fileno())
            if journal_metadata.st_mode & 0o077 or manifest_metadata.st_mode & 0o077:
                raise AuditSnapshotError(
                    "audit snapshot file permissions are not private"
                )
            try:
                manifest = json.loads(raw_manifest.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise AuditSnapshotError(
                    "audit snapshot manifest is invalid"
                ) from error
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != SCHEMA_VERSION
            ):
                raise AuditSnapshotError("audit snapshot manifest schema is invalid")
            if manifest.get(
                "size_bytes"
            ) != journal_metadata.st_size or stream_sha256_handle(
                journal
            ) != manifest.get(
                "sha256"
            ):
                raise AuditSnapshotError("audit snapshot integrity check failed")
            try:
                head_hash, record_count = read_audit_stream(journal)
            except AuditChainError as error:
                raise AuditSnapshotError(str(error)) from error
            if (
                manifest.get("record_count") != record_count
                or manifest.get("head_hash") != head_hash
            ):
                raise AuditSnapshotError("audit snapshot chain metadata does not match")
            journal.seek(0)
            yield manifest, journal
    except AuditSnapshotError:
        raise
    except PrivateFileError as error:
        raise AuditSnapshotError(str(error)) from error


def verify_snapshot(snapshot: Path) -> dict[str, object]:
    """Verify snapshot permissions, checksum, and audit-chain continuity."""
    with _verified_snapshot_source(snapshot) as (manifest, _journal):
        return manifest


def create_snapshot(journal: Path, backup_dir: Path) -> Path:
    """Atomically create one verified private audit snapshot."""
    try:
        with open_regular_file(journal, "audit journal") as source:
            source_metadata = os.fstat(source.fileno())
            if source_metadata.st_mode & 0o077:
                raise AuditSnapshotError("audit journal permissions are not private")
            try:
                source_head, source_count = read_audit_stream(source)
            except AuditChainError as error:
                raise AuditSnapshotError(str(error)) from error
            source_identity = _identity(source_metadata)
            with staging_directory(backup_dir, prefix=".audit-snapshot-") as staging:
                temporary = staging.path
                staged_journal = temporary / JOURNAL_NAME
                atomic_copy(
                    source,
                    staged_journal,
                    label="audit journal",
                    expected_identity=source_identity,
                )
                with open_regular_file(staged_journal, "snapshot journal") as staged:
                    staged_metadata = os.fstat(staged.fileno())
                    staged_digest = stream_sha256_handle(staged)
                manifest = {
                    "schema_version": SCHEMA_VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_name": journal.name,
                    "size_bytes": staged_metadata.st_size,
                    "sha256": staged_digest,
                    "record_count": source_count,
                    "head_hash": source_head,
                }
                write_private_manifest(temporary / MANIFEST_NAME, manifest)
                verify_snapshot(temporary)
                final = staging.publish(
                    f"snapshot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
                )
                return final
    except PrivateFileError as error:
        if str(error).startswith("audit journal changed"):
            raise AuditSnapshotError(
                "audit journal changed while snapshotting"
            ) from error
        raise AuditSnapshotError(
            f"audit snapshot directory is unsafe: {error}"
        ) from error


def restore_snapshot(
    snapshot: Path, journal: Path, *, replace_existing: bool = False
) -> None:
    """Restore a verified snapshot atomically, requiring explicit replacement."""
    try:
        with _verified_snapshot_source(snapshot) as (_manifest, source):
            atomic_copy(
                source,
                journal,
                label="snapshot journal",
                replace_existing=replace_existing,
            )
    except PrivateFileError as error:
        raise AuditSnapshotError(str(error)) from error


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
            restore_snapshot(
                args.snapshot, args.journal, replace_existing=args.replace_existing
            )
            print("audit journal snapshot restored")
    except (AuditSnapshotError, OSError) as error:
        print(f"audit snapshot failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
