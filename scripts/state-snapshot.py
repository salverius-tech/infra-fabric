#!/usr/bin/env python3
"""Create and validate private atomic snapshots of local OpenTofu state."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from private_files import (
        PrivateFileError,
        atomic_copy,
        ensure_private_directory,
        open_private_directory,
        open_regular_child,
        open_regular_file,
        staging_directory,
        stream_sha256,
        stream_sha256_handle,
        write_private_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - direct import in test loaders
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from private_files import (
        PrivateFileError,
        atomic_copy,
        ensure_private_directory,
        open_private_directory,
        open_regular_child,
        open_regular_file,
        staging_directory,
        stream_sha256,
        stream_sha256_handle,
        write_private_manifest,
    )

try:
    from site_lock import SiteLockError, acquire_site_lock
except ModuleNotFoundError:  # pragma: no cover - direct import in test loaders
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from site_lock import SiteLockError, acquire_site_lock


SCHEMA_VERSION = 1
DEFAULT_RETENTION = 10
STATE_NAME = "terraform.tfstate"
MANIFEST_NAME = "manifest.json"


class StateSnapshotError(RuntimeError):
    """Raised when a local-state snapshot operation cannot proceed safely."""


def _sha256(path: Path) -> str:
    try:
        return stream_sha256(path)
    except PrivateFileError as error:
        raise StateSnapshotError(str(error)) from error


def _validate_state_document(path: Path) -> None:
    try:
        with open_regular_file(path, "local state") as handle:
            _validate_state_stream(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StateSnapshotError("local state document is invalid") from error


def _validate_state_stream(handle) -> None:
    handle.seek(0)
    try:
        document = json.loads(handle.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StateSnapshotError("local state document is invalid") from error
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("version"), int)
        or document["version"] < 1
        or not isinstance(document.get("serial"), int)
        or document["serial"] < 0
        or not isinstance(document.get("resources"), list)
    ):
        raise StateSnapshotError("local state document structure is invalid")


def _private_directory(path: Path) -> None:
    try:
        ensure_private_directory(path)
    except PrivateFileError as error:
        raise StateSnapshotError(
            f"state snapshot directory is unsafe: {error}"
        ) from error


@contextlib.contextmanager
def _verified_snapshot_source(snapshot: Path):
    """Yield a manifest and state stream from one held directory identity."""
    try:
        with open_private_directory(
            snapshot, "state snapshot"
        ) as directory_fd, open_regular_child(
            directory_fd, STATE_NAME, "snapshot state"
        ) as state, open_regular_child(
            directory_fd, MANIFEST_NAME, "snapshot manifest"
        ) as raw_manifest:
            state_metadata = os.fstat(state.fileno())
            manifest_metadata = os.fstat(raw_manifest.fileno())
            if state_metadata.st_mode & 0o077 or manifest_metadata.st_mode & 0o077:
                raise StateSnapshotError(
                    "state snapshot file permissions are not private"
                )
            try:
                manifest = json.loads(raw_manifest.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise StateSnapshotError(
                    "state snapshot manifest is invalid"
                ) from error
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != SCHEMA_VERSION
            ):
                raise StateSnapshotError("state snapshot manifest schema is invalid")
            expected_hash, expected_size = manifest.get("sha256"), manifest.get(
                "size_bytes"
            )
            if not isinstance(expected_hash, str) or len(expected_hash) != 64:
                raise StateSnapshotError("state snapshot checksum metadata is invalid")
            if (
                expected_size != state_metadata.st_size
                or stream_sha256_handle(state) != expected_hash
            ):
                raise StateSnapshotError("state snapshot integrity check failed")
            _validate_state_stream(state)
            state.seek(0)
            yield manifest, state
    except StateSnapshotError:
        raise
    except PrivateFileError as error:
        raise StateSnapshotError("state snapshot is not a safe directory") from error


def verify_snapshot(snapshot: Path) -> dict[str, object]:
    """Validate one complete snapshot directory without exposing state content."""
    with _verified_snapshot_source(snapshot) as (manifest, _state):
        return manifest


def create_snapshot(
    state: Path, backup_dir: Path, *, retain: int = DEFAULT_RETENTION
) -> Path | None:
    """Atomically snapshot an existing local state file and enforce retention."""
    if retain < 1:
        raise StateSnapshotError("state snapshot retention must be positive")
    if not state.exists():
        return None
    try:
        with open_regular_file(state, "local state") as source:
            source_metadata = os.fstat(source.fileno())
            source_identity = (
                source_metadata.st_dev,
                source_metadata.st_ino,
                source_metadata.st_size,
                source_metadata.st_mtime_ns,
            )
            _validate_state_stream(source)
            with staging_directory(backup_dir, prefix=".snapshot-next-") as staging:
                temporary = staging.path
                snapshot_state = temporary / STATE_NAME
                atomic_copy(
                    source,
                    snapshot_state,
                    label="local state",
                    expected_identity=source_identity,
                )
                _validate_state_document(snapshot_state)
                digest = _sha256(snapshot_state)
                created_at = datetime.now(timezone.utc)
                manifest = {
                    "schema_version": SCHEMA_VERSION,
                    "created_at": created_at.isoformat(),
                    "source_name": state.name,
                    "sha256": digest,
                    "size_bytes": source_metadata.st_size,
                }
                write_private_manifest(temporary / MANIFEST_NAME, manifest)
                verify_snapshot(temporary)
                destination = staging.publish(
                    f"snapshot-{created_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest[:12]}"
                )
                staging.prune(prefix="snapshot-", retain=retain)
                return destination
    except PrivateFileError as error:
        if str(error).startswith("local state changed"):
            raise StateSnapshotError(
                "local state changed while snapshotting"
            ) from error
        raise StateSnapshotError(
            f"state snapshot directory is unsafe: {error}"
        ) from error


def restore_snapshot(
    snapshot: Path, state: Path, *, replace_existing: bool = False
) -> None:
    """Atomically restore a verified snapshot to a disposable or acknowledged state path."""
    try:
        with _verified_snapshot_source(snapshot) as (_manifest, source):
            try:
                atomic_copy(
                    source,
                    state,
                    label="snapshot state",
                    replace_existing=replace_existing,
                )
            except PrivateFileError as error:
                raise StateSnapshotError(str(error)) from error
    except PrivateFileError as error:
        raise StateSnapshotError(str(error)) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--state", type=Path, required=True)
    create.add_argument("--backup-dir", type=Path, required=True)
    create.add_argument("--retain", type=int, default=DEFAULT_RETENTION)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--snapshot", type=Path, required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--snapshot", type=Path, required=True)
    restore.add_argument("--state", type=Path, required=True)
    restore.add_argument("--lock-path", type=Path)
    restore.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "create":
            created = create_snapshot(args.state, args.backup_dir, retain=args.retain)
            print(
                "local state snapshot created"
                if created is not None
                else "local state snapshot skipped: state absent"
            )
        elif args.action == "verify":
            verify_snapshot(args.snapshot)
            print("local state snapshot verified")
        else:
            lock_path = args.lock_path or args.state.parent / ".infra-fabric.lock"
            with acquire_site_lock(lock_path):
                restore_snapshot(
                    args.snapshot, args.state, replace_existing=args.replace_existing
                )
            print("local state snapshot restored")
    except (SiteLockError, StateSnapshotError) as error:
        print(f"local state snapshot failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
