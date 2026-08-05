#!/usr/bin/env python3
"""Safely migrate identity-specific logical secret paths.

The migration operates on decrypted YAML only in memory or a private temporary
file. It never prints decrypted content. Encrypted bundles are changed only
when the caller explicitly requests ``apply=True``.
"""
from __future__ import annotations

import copy
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


LEGACY_OPERATOR_PATH = ("operator", "systemboss_password")
INTERIM_OPERATOR_PATH = ("operator", "password")
CANONICAL_OPERATOR_PATH = ("secrets", "operator", "password")


class SecretBundleMigrationError(ValueError):
    """Raised when a secret-bundle migration is unsafe or invalid."""


def _path_value(document: dict[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    value: Any = document
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _set_path(document: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    target = document
    for part in path[:-1]:
        child = target.setdefault(part, {})
        if not isinstance(child, dict):
            raise SecretBundleMigrationError("canonical secret namespace must be a mapping")
        target = child
    target[path[-1]] = value


def _delete_path(document: dict[str, Any], path: tuple[str, ...]) -> None:
    parents: list[tuple[dict[str, Any], str]] = []
    target: Any = document
    for part in path[:-1]:
        if not isinstance(target, dict) or part not in target:
            return
        parents.append((target, part))
        target = target[part]
    if not isinstance(target, dict):
        raise SecretBundleMigrationError("operator secret namespace must be a mapping")
    target.pop(path[-1], None)
    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            del parent[key]


def migrate_document(document: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Move accepted legacy operator-password aliases to the canonical path."""
    if not isinstance(document, dict):
        raise SecretBundleMigrationError("secret bundle must be a mapping")
    migrated = copy.deepcopy(document)
    candidates = (CANONICAL_OPERATOR_PATH, INTERIM_OPERATOR_PATH, LEGACY_OPERATOR_PATH)
    present: list[tuple[tuple[str, ...], Any]] = []
    for path in candidates:
        found, value = _path_value(migrated, path)
        if found:
            present.append((path, value))
    if not present:
        return migrated, False
    canonical_value = present[0][1]
    if not isinstance(canonical_value, str) or not canonical_value:
        raise SecretBundleMigrationError("operator secret must be a non-empty string")
    if any(value != canonical_value for _, value in present[1:]):
        raise SecretBundleMigrationError("legacy and canonical operator secrets conflict")
    canonical_present = any(path == CANONICAL_OPERATOR_PATH for path, _ in present)
    changed = not canonical_present or any(path != CANONICAL_OPERATOR_PATH for path, _ in present)
    _set_path(migrated, CANONICAL_OPERATOR_PATH, present[0][1])
    for path in (INTERIM_OPERATOR_PATH, LEGACY_OPERATOR_PATH):
        _delete_path(migrated, path)
    return migrated, changed


def _yaml_dump(document: dict[str, Any]) -> str:
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    from io import StringIO

    output = StringIO()
    yaml.dump(document, output)
    return output.getvalue()


def _run_sops(
    args: list[str],
    *,
    input_text: str | None = None,
    environment: dict[str, str] | None = None,
) -> str:
    env = os.environ.copy()
    if environment:
        env.update(environment)
    env.pop("SOPS_AGE_KEY", None)
    try:
        result = subprocess.run(
            args,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except OSError as error:
        raise SecretBundleMigrationError("SOPS executable is unavailable") from error
    if result.returncode != 0:
        raise SecretBundleMigrationError("SOPS secret-bundle migration command failed")
    return result.stdout


def migrate_encrypted_bundle(
    source: Path,
    *,
    output: Path | None = None,
    sops_executable: str = "sops",
    environment: dict[str, str] | None = None,
    apply: bool = False,
) -> dict[str, str | bool]:
    """Inspect or migrate one encrypted bundle without exposing its contents.

    Dry-run (the default) decrypts and validates the bundle but does not write
    any file. Apply mode re-encrypts to a private temporary file and atomically
    replaces the destination, retaining a ciphertext backup beside it.
    """
    source = source.expanduser().resolve()
    destination = (output or source).expanduser().resolve()
    if not source.is_file():
        raise SecretBundleMigrationError("secret bundle is unavailable")
    if not destination.parent.is_dir():
        raise SecretBundleMigrationError("secret bundle destination directory is unavailable")

    decrypted = _run_sops(
        [sops_executable, "--decrypt", "--input-type", "yaml", "--output-type", "yaml", str(source)],
        environment=environment,
    )
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    try:
        document = yaml.load(decrypted)
    except Exception as error:
        raise SecretBundleMigrationError("decrypted secret bundle is invalid") from error
    migrated, changed = migrate_document(document)
    result: dict[str, str | bool] = {
        "changed": changed,
        "source": str(source),
        "destination": str(destination),
        "source_ciphertext_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    if not changed or not apply:
        return result

    relative_name = os.path.relpath(destination, Path.cwd())
    with tempfile.TemporaryDirectory(prefix="canonical-secret-migration-") as temporary:
        temporary_dir = Path(temporary)
        plaintext = temporary_dir / "bundle.yaml"
        plaintext.write_text(_yaml_dump(migrated), encoding="utf-8")
        plaintext.chmod(0o600)
        encrypted = _run_sops(
            [
                sops_executable,
                "--encrypt",
                "--input-type",
                "yaml",
                "--output-type",
                "yaml",
                "--filename-override",
                relative_name,
                str(plaintext),
            ],
            environment=environment,
        )
        staged = temporary_dir / "bundle.sops.yaml"
        staged.write_text(encrypted, encoding="utf-8")
        staged.chmod(0o600)
        backup = destination.with_name(destination.name + ".pre-migration")
        if backup.exists():
            raise SecretBundleMigrationError("secret-bundle migration backup already exists")
        shutil.copy2(destination, backup)
        backup.chmod(0o600)
        os.replace(staged, destination)
    result["backup"] = str(backup)
    result["destination_ciphertext_sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
    return result


__all__ = [
    "CANONICAL_OPERATOR_PATH",
    "INTERIM_OPERATOR_PATH",
    "LEGACY_OPERATOR_PATH",
    "SecretBundleMigrationError",
    "migrate_document",
    "migrate_encrypted_bundle",
]
