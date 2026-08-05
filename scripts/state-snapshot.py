#!/usr/bin/env python3
"""Create and validate private atomic snapshots of local OpenTofu state."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

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


def _regular_file(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise StateSnapshotError(f"{label} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise StateSnapshotError(f"{label} must be a regular non-symlink file")
    return metadata


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_state_document(path: Path) -> None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
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
    if path.is_symlink():
        raise StateSnapshotError("state snapshot directory is unsafe")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise StateSnapshotError("state snapshot directory is unsafe")
    path.chmod(0o700)


def verify_snapshot(snapshot: Path) -> dict[str, object]:
    """Validate one complete snapshot directory without exposing state content."""
    if snapshot.is_symlink() or not snapshot.is_dir():
        raise StateSnapshotError("state snapshot is not a safe directory")
    if snapshot.stat().st_mode & 0o077:
        raise StateSnapshotError("state snapshot directory permissions are not private")
    state = snapshot / STATE_NAME
    manifest_path = snapshot / MANIFEST_NAME
    state_metadata = _regular_file(state, "snapshot state")
    _regular_file(manifest_path, "snapshot manifest")
    if state_metadata.st_mode & 0o077 or manifest_path.stat().st_mode & 0o077:
        raise StateSnapshotError("state snapshot file permissions are not private")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StateSnapshotError("state snapshot manifest is invalid") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise StateSnapshotError("state snapshot manifest schema is invalid")
    expected_hash = manifest.get("sha256")
    expected_size = manifest.get("size_bytes")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise StateSnapshotError("state snapshot checksum metadata is invalid")
    if expected_size != state_metadata.st_size or _sha256(state) != expected_hash:
        raise StateSnapshotError("state snapshot integrity check failed")
    _validate_state_document(state)
    return manifest


def _prune(backup_dir: Path, retain: int) -> None:
    snapshots = sorted(
        (
            entry
            for entry in backup_dir.iterdir()
            if entry.is_dir() and not entry.is_symlink() and entry.name.startswith("snapshot-")
        ),
        key=lambda entry: entry.name,
        reverse=True,
    )
    for expired in snapshots[retain:]:
        shutil.rmtree(expired)


def create_snapshot(state: Path, backup_dir: Path, *, retain: int = DEFAULT_RETENTION) -> Path | None:
    """Atomically snapshot an existing local state file and enforce retention."""
    if retain < 1:
        raise StateSnapshotError("state snapshot retention must be positive")
    if not state.exists():
        return None
    source_metadata = _regular_file(state, "local state")
    _validate_state_document(state)
    _private_directory(backup_dir)
    temporary = Path(tempfile.mkdtemp(prefix=".snapshot-next-", dir=backup_dir))
    temporary.chmod(0o700)
    try:
        snapshot_state = temporary / STATE_NAME
        with state.open("rb") as source, snapshot_state.open("xb") as destination:
            before = os.fstat(source.fileno())
            shutil.copyfileobj(source, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
            after = os.fstat(source.fileno())
        source_identity = (source_metadata.st_dev, source_metadata.st_ino, source_metadata.st_size, source_metadata.st_mtime_ns)
        if source_identity != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) or source_identity != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise StateSnapshotError("local state changed while snapshotting")
        snapshot_state.chmod(0o600)
        digest = _sha256(snapshot_state)
        created_at = datetime.now(timezone.utc)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": created_at.isoformat(),
            "source_name": state.name,
            "sha256": digest,
            "size_bytes": source_metadata.st_size,
        }
        manifest_path = temporary / MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path.chmod(0o600)
        verify_snapshot(temporary)
        destination = backup_dir / f"snapshot-{created_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest[:12]}"
        os.replace(temporary, destination)
        _prune(backup_dir, retain)
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def restore_snapshot(snapshot: Path, state: Path, *, replace_existing: bool = False) -> None:
    """Atomically restore a verified snapshot to a disposable or acknowledged state path."""
    verify_snapshot(snapshot)
    if state.exists() and not replace_existing:
        raise StateSnapshotError("local state already exists; explicit replacement acknowledgement is required")
    if state.parent.is_symlink() or not state.parent.is_dir():
        raise StateSnapshotError("local state parent directory is unsafe")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".terraform-state-restore-", dir=state.parent, delete=False) as handle:
            temporary = Path(handle.name)
            with (snapshot / STATE_NAME).open("rb") as source:
                shutil.copyfileobj(source, handle, length=1024 * 1024)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        if _sha256(temporary) != str(verify_snapshot(snapshot)["sha256"]):
            raise StateSnapshotError("restored state integrity check failed")
        os.replace(temporary, state)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
            print("local state snapshot created" if created is not None else "local state snapshot skipped: state absent")
        elif args.action == "verify":
            verify_snapshot(args.snapshot)
            print("local state snapshot verified")
        else:
            lock_path = args.lock_path or args.state.parent / ".infra-fabric.lock"
            with acquire_site_lock(lock_path):
                restore_snapshot(args.snapshot, args.state, replace_existing=args.replace_existing)
            print("local state snapshot restored")
    except (SiteLockError, StateSnapshotError) as error:
        print(f"local state snapshot failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
