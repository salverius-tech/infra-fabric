#!/usr/bin/env python3
"""Create a private read-only snapshot for one verified apply execution."""
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


SCHEMA_VERSION = 1
DEFAULT_RETENTION = 5
GENERATED_FILES = (
    "manifest.json",
    "terraform.auto.tfvars.json",
    "ansible-inventory.json",
    "ansible-vars.json",
    "dns-records.json",
)
SITE_FILES = ("site.yaml", "secrets.sops.yaml", ".sops.yaml")


class ExecutionSnapshotError(RuntimeError):
    """Raised when a verified execution snapshot cannot be created safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ExecutionSnapshotError("execution snapshot source is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ExecutionSnapshotError("execution snapshot source must be a regular non-symlink file")


def _copy(source: Path, destination: Path) -> None:
    _safe_source(source)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(source, flags)
    except OSError as error:
        raise ExecutionSnapshotError("execution snapshot source changed during copy") from error
    try:
        before = os.fstat(descriptor)
        with os.fdopen(descriptor, "rb", closefd=False) as input_file, destination.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
            output_file.flush()
            os.fsync(output_file.fileno())
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ExecutionSnapshotError("execution snapshot source changed during copy")
    destination.chmod(0o600)


def _expected_sources(values_dir: Path, plan: Path, metadata: Path) -> dict[str, Path]:
    sources = {
        "tfplan": plan,
        "tfplan.meta.json": metadata,
    }
    for name in SITE_FILES:
        sources[f"values/{name}"] = values_dir / name
    for name in GENERATED_FILES:
        sources[f"values/generated/{name}"] = values_dir / "generated" / name
    return sources


def verify_snapshot(snapshot: Path, *, sealed: bool = True) -> dict[str, object]:
    """Verify snapshot structure, permissions, and every copied file hash."""
    if snapshot.is_symlink() or not snapshot.is_dir():
        raise ExecutionSnapshotError("execution snapshot directory is unsafe")
    root = snapshot.resolve()
    directory_mode = root.stat().st_mode & 0o777
    expected_directory_mode = 0o500 if sealed else 0o700
    if directory_mode != expected_directory_mode:
        raise ExecutionSnapshotError("execution snapshot directory permissions are invalid")
    manifest_path = root / "execution-manifest.json"
    _safe_source(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExecutionSnapshotError("execution snapshot manifest is invalid") from error
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if manifest.get("schema_version") != SCHEMA_VERSION or not isinstance(files, dict) or not files:
        raise ExecutionSnapshotError("execution snapshot manifest schema is invalid")
    file_mode = 0o400 if sealed else 0o600
    if manifest_path.stat().st_mode & 0o777 != file_mode:
        raise ExecutionSnapshotError("execution snapshot manifest permissions are invalid")
    for relative, expected_hash in files.items():
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise ExecutionSnapshotError("execution snapshot manifest entries are invalid")
        path = root / relative
        if root not in path.resolve().parents:
            raise ExecutionSnapshotError("execution snapshot manifest path is unsafe")
        _safe_source(path)
        if path.stat().st_mode & 0o777 != file_mode or _sha256(path) != expected_hash:
            raise ExecutionSnapshotError("execution snapshot integrity check failed")
    return manifest


def _seal(snapshot: Path) -> None:
    for path in snapshot.rglob("*"):
        if path.is_symlink():
            raise ExecutionSnapshotError("execution snapshot contains a symlink")
        path.chmod(0o500 if path.is_dir() else 0o400)
    snapshot.chmod(0o500)


def _remove_snapshot(snapshot: Path) -> None:
    verify_snapshot(snapshot)
    for path in sorted(snapshot.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o700 if path.is_dir() else 0o600)
    snapshot.chmod(0o700)
    shutil.rmtree(snapshot)


def _prune(destination_root: Path, retain: int) -> None:
    snapshots = sorted(
        (
            entry
            for entry in destination_root.iterdir()
            if entry.is_dir() and not entry.is_symlink() and entry.name.startswith("execution-")
        ),
        key=lambda entry: entry.name,
        reverse=True,
    )
    for expired in snapshots[retain:]:
        _remove_snapshot(expired)


def create_snapshot(
    values_dir: Path,
    plan: Path,
    metadata: Path,
    destination_root: Path,
    *,
    site: str,
    retain: int = DEFAULT_RETENTION,
) -> Path:
    """Copy verified execution inputs into one atomically installed read-only directory."""
    if not site or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in site):
        raise ExecutionSnapshotError("execution snapshot site is invalid")
    if retain < 1:
        raise ExecutionSnapshotError("execution snapshot retention must be positive")
    if destination_root.is_symlink():
        raise ExecutionSnapshotError("execution snapshot root is unsafe")
    destination_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination_root.chmod(0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".execution-next-", dir=destination_root))
    temporary.chmod(0o700)
    try:
        sources = _expected_sources(values_dir, plan, metadata)
        files: dict[str, str] = {}
        for relative, source in sources.items():
            if relative.startswith("values/"):
                destination = temporary / "values" / "sites" / site / relative.removeprefix("values/")
                manifest_relative = destination.relative_to(temporary).as_posix()
            else:
                destination = temporary / relative
                manifest_relative = relative
            _copy(source, destination)
            files[manifest_relative] = _sha256(destination)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "site": site,
            "files": dict(sorted(files.items())),
        }
        manifest_path = temporary / "execution-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path.chmod(0o600)
        verify_snapshot(temporary, sealed=False)
        final = destination_root / f"execution-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{files['tfplan'][:12]}"
        os.replace(temporary, final)
        _seal(final)
        verify_snapshot(final)
        _prune(destination_root, retain)
        return final
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--values-dir", type=Path, required=True)
    create.add_argument("--plan", type=Path, required=True)
    create.add_argument("--metadata", type=Path, required=True)
    create.add_argument("--destination-root", type=Path, required=True)
    create.add_argument("--site", required=True)
    create.add_argument("--retain", type=int, default=DEFAULT_RETENTION)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "create":
            snapshot = create_snapshot(
                args.values_dir,
                args.plan,
                args.metadata,
                args.destination_root,
                site=args.site,
                retain=args.retain,
            )
            print(snapshot)
        else:
            verify_snapshot(args.snapshot)
            print("execution snapshot verified")
    except ExecutionSnapshotError as error:
        print(f"execution snapshot failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
