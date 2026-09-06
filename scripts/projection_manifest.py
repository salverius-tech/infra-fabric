#!/usr/bin/env python3
"""Stable identity manifests for canonical consumer projections."""
from __future__ import annotations

import hashlib
import json
import stat
from datetime import datetime, timezone
from typing import Any


class ManifestError(ValueError):
    """Raised for invalid projection data or identity metadata."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ManifestError("projection data is not JSON-compatible") from error


def content_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def build_manifest(
    *,
    site: str,
    schema_version: int,
    model_digest: str,
    secret_digest: str | None,
    projections: dict[str, Any],
    renderer_version: str,
    source_commit: str,
) -> dict[str, Any]:
    if not site or not model_digest or not renderer_version or not source_commit:
        raise ManifestError("site, model digest, renderer version, and source commit are required")
    projection_entries = {
        name: {"digest": content_digest(value), "secret_bearing": name in {"runtime.env"}}
        for name, value in sorted(projections.items())
    }
    manifest = {
        "site": site,
        "schema_version": schema_version,
        "model_digest": model_digest,
        "secret_digest": secret_digest,
        "renderer_version": renderer_version,
        "source_commit": source_commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "projections": projection_entries,
    }
    manifest["projection_digest"] = content_digest({key: value for key, value in manifest.items() if key != "created_at"})
    return manifest


def verify_manifest(
    manifest: dict[str, Any],
    *,
    site: str,
    model_digest: str,
    secret_digest: str | None,
    projections: dict[str, Any],
) -> None:
    if manifest.get("site") != site:
        raise ManifestError("projection manifest belongs to a different site")
    if manifest.get("model_digest") != model_digest:
        raise ManifestError("projection manifest has a stale model digest")
    if manifest.get("secret_digest") != secret_digest:
        raise ManifestError("projection manifest has a stale secret digest")
    recorded_digest = manifest.get("projection_digest")
    if not isinstance(recorded_digest, str):
        raise ManifestError("projection manifest has no projection digest")
    unsigned_manifest = {key: value for key, value in manifest.items() if key not in {"created_at", "projection_digest"}}
    unsigned_manifest["projection_digest"] = recorded_digest
    expected_digest = content_digest({key: value for key, value in unsigned_manifest.items() if key != "projection_digest"})
    if expected_digest != recorded_digest:
        raise ManifestError("projection manifest identity is altered")
    entries = manifest.get("projections")
    if not isinstance(entries, dict):
        raise ManifestError("projection manifest has no projection entries")
    if set(entries) != set(projections):
        raise ManifestError("projection manifest projection set does not match")
    for name, value in projections.items():
        entry = entries.get(name)
        if not isinstance(entry, dict) or entry.get("digest") != content_digest(value):
            raise ManifestError(f"projection is stale or altered: {name}")


def verify_projection_permissions(directory: Any) -> None:
    if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise ManifestError("generated projection directory must be mode 0700")
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ManifestError(f"generated projection file must be a regular mode-0600 file: {path.name}")


__all__ = ["ManifestError", "build_manifest", "content_digest", "verify_manifest", "verify_projection_permissions"]
