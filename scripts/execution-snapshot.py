#!/usr/bin/env python3
"""Create a private read-only snapshot for one verified apply execution."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from private_files import (
        PrivateFileError,
        atomic_copy,
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
        open_private_directory,
        open_regular_child,
        open_regular_file,
        staging_directory,
        stream_sha256,
        stream_sha256_handle,
        write_private_manifest,
    )


SCHEMA_VERSION = 1
DEFAULT_RETENTION = 5
GENERATED_FILES = (
    "manifest.json",
    "terraform.auto.tfvars.json",
    "ansible-inventory.json",
    "ansible-vars.json",
    "dns-records.json",
    "onramp-handoff.json",
)
SITE_FILES = ("site.yaml", "secrets.sops.yaml", ".sops.yaml")


class ExecutionSnapshotError(RuntimeError):
    """Raised when a verified execution snapshot cannot be created safely."""


def _sha256(path: Path) -> str:
    try:
        return stream_sha256(path, "execution snapshot file")
    except PrivateFileError as error:
        raise ExecutionSnapshotError(str(error)) from error


def _copy(source, destination: Path) -> None:
    try:
        atomic_copy(source, destination, label="execution snapshot source")
    except PrivateFileError as error:
        raise ExecutionSnapshotError(str(error)) from error


def _expected_sources(
    values_dir: Path, plan: Path, metadata: Path, generated_dir: Path | None = None
) -> dict[str, Path]:
    sources = {
        "tfplan": plan,
        "tfplan.meta.json": metadata,
    }
    for name in SITE_FILES:
        sources[f"values/{name}"] = values_dir / name
    projections = generated_dir or values_dir / "generated"
    for name in GENERATED_FILES:
        sources[f"values/generated/{name}"] = projections / name
    return sources


def _relative_components(relative: str) -> tuple[str, ...]:
    """Reject manifest paths that could escape a held snapshot descriptor."""
    if not relative or relative.startswith("/"):
        raise ExecutionSnapshotError("execution snapshot manifest path is unsafe")
    components = tuple(relative.split("/"))
    if any(component in {"", ".", ".."} for component in components):
        raise ExecutionSnapshotError("execution snapshot manifest path is unsafe")
    return components


@contextlib.contextmanager
def _open_snapshot_file(root_fd: int, relative: str):
    """Open a lexically-safe nested regular child from one held root FD."""
    components = _relative_components(relative)
    descriptors: list[int] = []
    parent_fd = root_fd
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        for component in components[:-1]:
            descriptor = os.open(component, directory_flags, dir_fd=parent_fd)
            descriptors.append(descriptor)
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise ExecutionSnapshotError(
                    "execution snapshot manifest path is unsafe"
                )
            parent_fd = descriptor
        with open_regular_child(
            parent_fd, components[-1], "execution snapshot file"
        ) as handle:
            yield handle
    except ExecutionSnapshotError:
        raise
    except (OSError, PrivateFileError) as error:
        raise ExecutionSnapshotError(
            "execution snapshot manifest path is unsafe"
        ) from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def verify_snapshot(snapshot: Path, *, sealed: bool = True) -> dict[str, object]:
    """Verify snapshot structure, permissions, and every copied file hash."""
    try:
        with open_private_directory(snapshot, "execution snapshot") as root_fd:
            directory_mode = os.fstat(root_fd).st_mode & 0o777
            expected_directory_mode = 0o500 if sealed else 0o700
            if directory_mode != expected_directory_mode:
                raise ExecutionSnapshotError(
                    "execution snapshot directory permissions are invalid"
                )
            try:
                with open_regular_child(
                    root_fd, "execution-manifest.json", "execution snapshot manifest"
                ) as handle:
                    manifest = json.loads(handle.read().decode("utf-8"))
                    manifest_mode = os.fstat(handle.fileno()).st_mode & 0o777
            except (
                PrivateFileError,
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as error:
                raise ExecutionSnapshotError(
                    "execution snapshot manifest is invalid"
                ) from error
            files = manifest.get("files") if isinstance(manifest, dict) else None
            if (
                manifest.get("schema_version") != SCHEMA_VERSION
                or not isinstance(files, dict)
                or not files
            ):
                raise ExecutionSnapshotError(
                    "execution snapshot manifest schema is invalid"
                )
            file_mode = 0o400 if sealed else 0o600
            if manifest_mode != file_mode:
                raise ExecutionSnapshotError(
                    "execution snapshot manifest permissions are invalid"
                )
            for relative, expected_hash in files.items():
                if not isinstance(relative, str) or not isinstance(expected_hash, str):
                    raise ExecutionSnapshotError(
                        "execution snapshot manifest entries are invalid"
                    )
                with _open_snapshot_file(root_fd, relative) as handle:
                    mode = os.fstat(handle.fileno()).st_mode & 0o777
                    actual_hash = stream_sha256_handle(handle)
                if mode != file_mode or actual_hash != expected_hash:
                    raise ExecutionSnapshotError(
                        "execution snapshot integrity check failed"
                    )
            return manifest
    except PrivateFileError as error:
        raise ExecutionSnapshotError(
            "execution snapshot directory is unsafe"
        ) from error


def _seal_tree(directory_fd: int) -> None:
    """Seal an already-held snapshot tree without reopening path spellings."""
    for name in os.listdir(directory_fd):
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            try:
                _seal_tree(descriptor)
                os.fchmod(descriptor, 0o500)
            finally:
                os.close(descriptor)
        elif stat.S_ISREG(metadata.st_mode):
            descriptor = os.open(
                name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd
            )
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise ExecutionSnapshotError(
                        "execution snapshot contains a symlink"
                    )
                os.fchmod(descriptor, 0o400)
            finally:
                os.close(descriptor)
        else:
            raise ExecutionSnapshotError("execution snapshot contains a symlink")


def _seal(snapshot: Path) -> None:
    try:
        with open_private_directory(snapshot, "execution snapshot") as root_fd:
            _seal_tree(root_fd)
            os.fchmod(root_fd, 0o500)
    except PrivateFileError as error:
        raise ExecutionSnapshotError("execution snapshot contains a symlink") from error


def create_snapshot(
    values_dir: Path,
    plan: Path,
    metadata: Path,
    destination_root: Path,
    *,
    site: str,
    generated_dir: Path | None = None,
    retain: int = DEFAULT_RETENTION,
) -> Path:
    """Copy verified execution inputs into one atomically installed read-only directory."""
    if not site or any(
        character
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for character in site
    ):
        raise ExecutionSnapshotError("execution snapshot site is invalid")
    if retain < 1:
        raise ExecutionSnapshotError("execution snapshot retention must be positive")
    try:
        with staging_directory(destination_root, prefix=".execution-next-") as staging:
            temporary = staging.path
            sources = _expected_sources(values_dir, plan, metadata, generated_dir)
            files: dict[str, str] = {}
            for relative, source in sources.items():
                if relative.startswith("values/"):
                    destination = (
                        temporary
                        / "values"
                        / "sites"
                        / site
                        / relative.removeprefix("values/")
                    )
                    manifest_relative = destination.relative_to(temporary).as_posix()
                else:
                    destination = temporary / relative
                    manifest_relative = relative
                with open_regular_file(
                    source, "execution snapshot source"
                ) as held_source:
                    _copy(held_source, destination)
                files[manifest_relative] = _sha256(destination)
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "site": site,
                "files": dict(sorted(files.items())),
            }
            write_private_manifest(temporary / "execution-manifest.json", manifest)
            verify_snapshot(temporary, sealed=False)
            _seal(temporary)
            verify_snapshot(temporary)
            final = staging.publish(
                f"execution-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{files['tfplan'][:12]}"
            )
            verify_snapshot(final)
            staging.prune(prefix="execution-", retain=retain)
            return final
    except PrivateFileError as error:
        raise ExecutionSnapshotError(str(error)) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--values-dir", type=Path, required=True)
    create.add_argument("--plan", type=Path, required=True)
    create.add_argument("--metadata", type=Path, required=True)
    create.add_argument("--destination-root", type=Path, required=True)
    create.add_argument("--generated-dir", type=Path)
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
                generated_dir=args.generated_dir,
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
