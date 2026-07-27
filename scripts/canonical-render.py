#!/usr/bin/env python3
"""Render disposable non-secret canonical consumer projections."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from canonical_projections import render_ansible_inventory, render_dns_records, render_opentofu_variables
from canonical_values import CanonicalValuesError, load_site, model_digest
from projection_manifest import ManifestError, build_manifest
from service_catalog import ServiceCatalogError, load_catalog


PROJECTION_FILES = {
    "terraform.auto.tfvars.json": "terraform",
    "ansible-inventory.json": "ansible",
    "dns-records.json": "dns",
}


def _write_json(path: Path, value: object) -> None:
    handle = tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", delete=False, encoding="utf-8")
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.chmod(0o600)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-file", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[1] / "infra" / "services.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", default=os.environ.get("INFRA_GIT_COMMIT", "unknown"))
    parser.add_argument("--renderer-version", default="canonical-renderer/0.1")
    args = parser.parse_args(argv)
    try:
        model = load_site(args.site_file, catalog_path=args.catalog)
        catalog = load_catalog(args.catalog)
        projections = {
            "terraform.auto.tfvars.json": render_opentofu_variables(model),
            "ansible-inventory.json": render_ansible_inventory(model, catalog),
            "dns-records.json": render_dns_records(model),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        args.output_dir.chmod(0o700)
        for name, value in projections.items():
            _write_json(args.output_dir / name, value)
        manifest = build_manifest(
            site=model.site.name,
            schema_version=model.schema_version,
            model_digest=model_digest(model),
            secret_digest=None,
            projections=projections,
            renderer_version=args.renderer_version,
            source_commit=args.source_commit,
        )
        _write_json(args.output_dir / "manifest.json", manifest)
        print(f"rendered {len(projections)} non-secret projections for {model.site.name} into {args.output_dir}")
    except (CanonicalValuesError, ServiceCatalogError, ManifestError, OSError, ValueError) as error:
        print(f"canonical projection error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
