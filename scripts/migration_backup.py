"""Deterministic, content-free manifests for migration backup rehearsal."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


class BackupManifestError(ValueError):
    """Raised when a backup manifest or tree is unsafe or inconsistent."""


def _relative_path(value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise BackupManifestError("backup paths must be non-empty relative strings")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise BackupManifestError("backup paths must remain within the backup root")
    return path


def _source_path(root: Path, relative: str) -> Path:
    path = root / _relative_path(relative)
    try:
        path.resolve(strict=True).relative_to(root.resolve())
    except (FileNotFoundError, ValueError) as error:
        raise BackupManifestError("backup paths must remain within the backup root") from error
    return path


def _file_entry(root: Path, relative: str) -> dict[str, Any]:
    relative = _relative_path(relative).as_posix()
    path = _source_path(root, relative)
    if not path.is_file() or path.is_symlink():
        raise BackupManifestError("backup entries must be regular files")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": relative, "type": "file", "size": path.stat().st_size, "sha256": digest}


def expand_backup_paths(root: Path, relative_paths: list[str]) -> list[str]:
    """Expand selected files/directories into unique, sorted POSIX file paths.

    Empty directories contribute no entries. A symlink or non-regular file
    anywhere below a selected directory is rejected rather than followed or
    silently omitted. Overlapping selections are harmless: each canonical
    relative path is returned once.
    """
    if not root.is_dir() or root.is_symlink():
        raise BackupManifestError("backup root must be a directory")

    selected: set[str] = set()

    def visit(path: Path, relative: str) -> None:
        if path.is_symlink():
            raise BackupManifestError("backup entries must not be symlinks")
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                visit(child, f"{relative}/{child.name}" if relative else child.name)
            return
        if not path.is_file():
            raise BackupManifestError("backup entries must be regular files")
        selected.add(_relative_path(relative).as_posix())

    for value in relative_paths:
        relative = _relative_path(value).as_posix()
        visit(_source_path(root, relative), relative)
    return sorted(selected)


def build_manifest(root: Path, relative_paths: list[str]) -> dict[str, Any]:
    entries = [_file_entry(root, path) for path in relative_paths]
    if len({entry["path"] for entry in entries}) != len(entries):
        raise BackupManifestError("backup paths must be unique")
    entries.sort(key=lambda entry: entry["path"])
    return {"schema_version": 1, "entries": entries}


def verify_manifest(root: Path, manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise BackupManifestError("unsupported backup manifest")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise BackupManifestError("backup manifest entries are invalid")
    expected: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "type", "size", "sha256"}:
            raise BackupManifestError("backup manifest entry is invalid")
        if entry["type"] != "file" or not isinstance(entry["size"], int) or not isinstance(entry["sha256"], str):
            raise BackupManifestError("backup manifest entry is invalid")
        expected.append(_file_entry(root, entry["path"]))
    if entries != sorted(entries, key=lambda item: item["path"]):
        raise BackupManifestError("backup manifest entries are not sorted")
    if expected != entries:
        raise BackupManifestError("backup tree differs from manifest")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BackupManifestError("backup tree contains symlinks")
    actual_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )
    if actual_paths != [entry["path"] for entry in entries]:
        raise BackupManifestError("backup tree contains unexpected files")


def _stage_selected_files(root: Path, relative_paths: list[str], staging: Path) -> None:
    """Copy selected regular files into a disposable tree."""
    if not root.is_dir() or root.is_symlink():
        raise BackupManifestError("backup root must be a directory")
    for relative in relative_paths:
        source = _source_path(root, relative)
        if not source.is_file() or source.is_symlink():
            raise BackupManifestError("selected backup entries must be regular files")
        destination = staging / _relative_path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _write_new_output(output: Path, manifest: dict[str, Any]) -> None:
    """Create a manifest without replacing an existing path."""
    if output.exists() or output.is_symlink():
        raise BackupManifestError("backup manifest output already exists")
    if not output.parent.is_dir():
        raise BackupManifestError("backup manifest output directory does not exist")
    content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        output.unlink(missing_ok=True)
        raise BackupManifestError("could not create backup manifest output") from error


def emit_manifest(root: Path, relative_paths: list[str], output: Path) -> dict[str, Any]:
    """Dry-run only: stage selected files and emit their content-free manifest."""
    expanded_paths = expand_backup_paths(root, relative_paths)
    with tempfile.TemporaryDirectory(prefix="migration-backup-") as directory:
        staging = Path(directory)
        _stage_selected_files(root, expanded_paths, staging)
        manifest = build_manifest(staging, expanded_paths)
    _write_new_output(output, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="source values tree (never modified)")
    parser.add_argument("--output", type=Path, required=True, help="new manifest path (must not already exist)")
    parser.add_argument("paths", nargs="+", help="selected files or directories relative to --root")
    args = parser.parse_args(argv)
    try:
        emit_manifest(args.root, args.paths, args.output)
    except (BackupManifestError, OSError) as error:
        print(f"migration backup failed: {error}", file=sys.stderr)
        return 1
    print(f"migration backup manifest written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
