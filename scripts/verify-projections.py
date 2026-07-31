#!/usr/bin/env python3
"""Verify installed canonical consumer projections against their site identity."""
from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path

from canonical_values import CanonicalValuesError, load_site, model_digest
from projection_manifest import ManifestError, verify_manifest
from service_catalog import ServiceCatalogError, load_catalog

PROJECTION_FILES = (
    "terraform.auto.tfvars.json",
    "ansible-inventory.json",
    "ansible-vars.json",
    "dns-records.json",
)


def verify_permissions(directory: Path) -> None:
    if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise ManifestError("generated projection directory must be mode 0700")
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ManifestError(f"generated projection file must be a regular mode-0600 file: {path.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-file", type=Path, required=True)
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[1] / "infra" / "services.json")
    args = parser.parse_args(argv)
    try:
        model = load_site(args.site_file, catalog_path=args.catalog)
        load_catalog(args.catalog)
        verify_permissions(args.generated_dir)
        manifest = json.loads((args.generated_dir / "manifest.json").read_text(encoding="utf-8"))
        projections = {
            name: json.loads((args.generated_dir / name).read_text(encoding="utf-8"))
            for name in PROJECTION_FILES
        }
        verify_manifest(
            manifest,
            site=model.site.name,
            model_digest=model_digest(model),
            secret_digest=None,
            projections=projections,
        )
    except (CanonicalValuesError, ServiceCatalogError, ManifestError, OSError, json.JSONDecodeError) as error:
        print(f"canonical projection verification failed: {error}", file=sys.stderr)
        return 1
    print(f"verified canonical projections for {model.site.name} in {args.generated_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
