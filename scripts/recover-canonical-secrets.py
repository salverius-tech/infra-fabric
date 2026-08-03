#!/usr/bin/env python3
"""Explicit, bounded recovery of selected legacy dotenv secrets into SOPS.

This transition command is never called by setup, validation, planning, or
apply. It reads only values/.env from private Git HEAD into a mode-0700 temporary
workspace. Canonical targets always win; differing legacy values produce only a
logical-path warning.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from secret_bundle_migration import SecretBundleMigrationError, _run_sops, _yaml_dump

ALLOWED_LEGACY_PATHS = frozenset({".env"})
ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


class RecoveryError(ValueError):
    pass


def parse_mapping(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise RecoveryError("recovery mapping must be LEGACY_ENV=canonical.logical.path")
    source, target = raw.split("=", 1)
    if not ENV_LINE.match(f"{source}=x") or not re.fullmatch(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+", target):
        raise RecoveryError("recovery mapping is invalid")
    return source, target


def legacy_env_from_head(values_root: Path) -> dict[str, str]:
    """Read the allow-listed legacy dotenv only into a restrictive temp workspace."""
    relative = ".env"
    if relative not in ALLOWED_LEGACY_PATHS:
        raise RecoveryError("legacy recovery source is not allow-listed")
    result = subprocess.run(["git", "-C", str(values_root), "show", f"HEAD:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise RecoveryError("allow-listed legacy source is unavailable from private Git HEAD")
    with tempfile.TemporaryDirectory(prefix="canonical-legacy-recovery-") as temporary:
        workspace = Path(temporary)
        workspace.chmod(0o700)
        source = workspace / "legacy.env"
        source.write_bytes(result.stdout)
        source.chmod(0o600)
        values: dict[str, str] = {}
        for line in source.read_text(encoding="utf-8").splitlines():
            match = ENV_LINE.match(line.strip())
            if match:
                values[match.group(1)] = match.group(2).strip().strip("'\"")
        return values


def _lookup(document: dict[str, Any], path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _set(document: dict[str, Any], path: str, value: str) -> None:
    parent: dict[str, Any] = document
    parts = path.split(".")
    for part in parts[:-1]:
        child = parent.setdefault(part, {})
        if not isinstance(child, dict):
            raise RecoveryError("canonical secret target namespace is invalid")
        parent = child
    parent[parts[-1]] = value


def recover(values_root: Path, bundle: Path, mappings: list[tuple[str, str]], *, apply: bool, sops: str) -> list[str]:
    legacy = legacy_env_from_head(values_root)
    decrypted = _run_sops([sops, "--decrypt", "--input-type", "yaml", "--output-type", "yaml", str(bundle)])
    document = YAML(typ="safe").load(decrypted)
    if not isinstance(document, dict):
        raise RecoveryError("canonical secret bundle is invalid")
    changed = False
    report: list[str] = []
    for source, target in mappings:
        old, current = legacy.get(source), _lookup(document, target)
        if current is not None:
            report.append(f"retained canonical target: {target}" if old == current else f"canonical target supersedes legacy source: {target}")
        elif old is None:
            report.append(f"missing recoverable source and canonical target: {target}")
        else:
            _set(document, target, old)
            changed = True
            report.append(f"imported missing canonical target: {target}")
    if changed and apply:
        encrypted = _run_sops([sops, "--encrypt", "--input-type", "yaml", "--output-type", "yaml", "--filename-override", str(bundle), "-"], input_text=_yaml_dump(document))
        staged = bundle.with_name(f".{bundle.name}.recovery-next")
        staged.write_text(encrypted, encoding="utf-8")
        staged.chmod(0o600)
        os.replace(staged, bundle)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--map", action="append", default=[], dest="mappings")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--sops", default="sops")
    args = parser.parse_args(argv)
    try:
        mappings = [parse_mapping(raw) for raw in args.mappings]
        if not mappings:
            raise RecoveryError("at least one explicit recovery mapping is required")
        for entry in recover(args.values_root, args.bundle, mappings, apply=args.apply, sops=args.sops):
            print(entry)
    except (RecoveryError, SecretBundleMigrationError) as error:
        print(f"canonical legacy recovery failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
