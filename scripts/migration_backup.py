"""Deterministic, content-free manifests for migration backup rehearsal."""
from __future__ import annotations

import hashlib
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


def _file_entry(root: Path, relative: str) -> dict[str, Any]:
    path = root / _relative_path(relative)
    if not path.is_file() or path.is_symlink():
        raise BackupManifestError("backup entries must be regular files")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": relative, "type": "file", "size": path.stat().st_size, "sha256": digest}


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
    actual_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    if actual_paths != [entry["path"] for entry in entries]:
        raise BackupManifestError("backup tree contains unexpected files")
