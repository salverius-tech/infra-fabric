#!/usr/bin/env python3
"""Safely check or atomically set one logical value in a SOPS YAML bundle."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruamel.yaml import YAML

from secret_provider import (
    SopsAgeProvider,
    SecretProviderError,
    canonical_sops_filename,
    validate_canonical_secret_path,
)


class SecretSetError(RuntimeError):
    """Raised when a canonical encrypted secret cannot be updated safely."""


def yaml_parser() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def set_path(data: dict[str, Any], path: str, value: str) -> None:
    current: dict[str, Any] = data
    parts = path.split(".")
    if any(not part for part in parts):
        raise SecretSetError("logical secret path is invalid")
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise SecretSetError("logical secret namespace is not a mapping")
        current = child
    current[parts[-1]] = value


def encrypt(sops: str, bundle: Path, data: dict[str, Any], key_file: Path) -> bytes:
    from io import StringIO

    plaintext = StringIO()
    yaml_parser().dump(data, plaintext)
    environment = os.environ.copy()
    environment["SOPS_AGE_KEY_FILE"] = str(key_file)
    result = subprocess.run(
        [
            sops,
            "--encrypt",
            "--input-type",
            "yaml",
            "--output-type",
            "yaml",
            "--filename-override",
            canonical_sops_filename(bundle),
            "--config",
            str(bundle.parent / ".sops.yaml"),
            "/dev/stdin",
        ],
        input=plaintext.getvalue(),
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise SecretSetError("SOPS encryption failed")
    return result.stdout.encode("utf-8")


def set_secret(bundle: Path, path: str, value: str, key_file: Path, *, replace: bool, sops: str) -> str:
    if not value or "\n" in value or "\r" in value:
        raise SecretSetError("secret value is empty or multiline")
    try:
        validate_canonical_secret_path(path)
    except SecretProviderError as error:
        raise SecretSetError("logical secret path is outside the canonical namespace") from error
    if not bundle.is_file() or not key_file.is_file():
        raise SecretSetError("canonical SOPS bundle or external age identity is unavailable")
    try:
        provider = SopsAgeProvider(bundle, key_file=key_file)
        existing = provider.resolve(path) if path in provider.discover() else None
        data = provider._data.copy()
    except (SecretProviderError, OSError) as error:
        raise SecretSetError("existing SOPS bundle could not be decrypted") from error
    if existing is not None and existing == value:
        return "already set"
    if existing is not None and not replace:
        raise SecretSetError("canonical secret already exists; use rotation explicitly")
    set_path(data, path, value)
    ciphertext = encrypt(sops, bundle, data, key_file)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=bundle.parent, prefix=f".{bundle.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(ciphertext)
        os.chmod(temporary, 0o600)
        os.replace(temporary, bundle)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "updated"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--key-file", type=Path, default=Path(os.environ.get("SOPS_AGE_KEY_FILE", "")))
    parser.add_argument("--value-env")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--sops", default="sops")
    args = parser.parse_args(argv)
    try:
        provider = SopsAgeProvider(args.bundle, key_file=args.key_file)
        present = args.path in provider.discover()
        if args.check:
            print("present" if present else "missing")
            return 0 if present else 1
        if not args.value_env:
            parser.error("--value-env is required unless --check is used")
        value = os.environ.get(args.value_env, "")
        print(set_secret(args.bundle, args.path, value, args.key_file, replace=args.replace, sops=args.sops))
    except (SecretProviderError, SecretSetError, OSError, ValueError) as error:
        print(f"canonical secret update failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
