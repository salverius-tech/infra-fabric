#!/usr/bin/env python3
"""Dry-run-by-default encrypted canonical secret-bundle migration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from secret_bundle_migration import SecretBundleMigrationError, migrate_encrypted_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="encrypted site secret bundle")
    parser.add_argument("--output", type=Path, help="destination bundle; defaults to replacing the source")
    parser.add_argument("--sops", default="sops", help="SOPS executable")
    parser.add_argument("--apply", action="store_true", help="write the migrated encrypted bundle")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = migrate_encrypted_bundle(
            args.bundle,
            output=args.output,
            sops_executable=args.sops,
            apply=args.apply,
        )
    except SecretBundleMigrationError as error:
        print(f"secret-bundle migration failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    if not args.apply:
        print("dry-run only; rerun with --apply to write the encrypted bundle", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
