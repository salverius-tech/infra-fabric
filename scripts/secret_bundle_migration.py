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
CANONICAL_OPERATOR_PATH = ("operator", "password")


class SecretBundleMigrationError(ValueError):
    """Raised when a secret-bundle migration is unsafe or invalid."""


def migrate_document(document: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Move the legacy operator password key to the canonical logical path."""
    if not isinstance(document, dict):
        raise SecretBundleMigrationError("secret bundle must be a mapping")
    migrated = copy.deepcopy(document)
    operator = migrated.get("operator")
    if operator is None:
        return migrated, False
    if not isinstance(operator, dict):
        raise SecretBundleMigrationError("operator secret namespace must be a mapping")
    legacy_present = LEGACY_OPERATOR_PATH[1] in operator
    canonical_present = CANONICAL_OPERATOR_PATH[1] in operator
    if not legacy_present:
        return migrated, False
    if canonical_present and operator[LEGACY_OPERATOR_PATH[1]] != operator[CANONICAL_OPERATOR_PATH[1]]:
        raise SecretBundleMigrationError("legacy and canonical operator secrets conflict")
    operator[CANONICAL_OPERATOR_PATH[1]] = operator[LEGACY_OPERATOR_PATH[1]]
    del operator[LEGACY_OPERATOR_PATH[1]]
    return migrated, True


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
    "LEGACY_OPERATOR_PATH",
    "SecretBundleMigrationError",
    "migrate_document",
    "migrate_encrypted_bundle",
]
