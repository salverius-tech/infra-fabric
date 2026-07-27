#!/usr/bin/env python3
"""Stable identity manifests for canonical consumer projections."""
from __future__ import annotations

import hashlib
import json
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
    entries = manifest.get("projections")
    if not isinstance(entries, dict):
        raise ManifestError("projection manifest has no projection entries")
    for name, value in projections.items():
        entry = entries.get(name)
        if not isinstance(entry, dict) or entry.get("digest") != content_digest(value):
            raise ManifestError(f"projection is stale or altered: {name}")


__all__ = ["ManifestError", "build_manifest", "content_digest", "verify_manifest"]
