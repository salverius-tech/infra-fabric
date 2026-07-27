#!/usr/bin/env python3
"""Validate and summarize a canonical site model without exposing secrets."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from canonical_values import CanonicalValuesError, load_site, redacted_summary


def _default_site_path() -> Path:
    repo = Path(__file__).resolve().parents[1]
    site = os.environ.get("VALUES_SITE")
    if not site:
        raise CanonicalValuesError("VALUES_SITE is required unless --site-file is provided")
    values_root = Path(os.environ.get("VALUES_DIR", repo / "values")).expanduser()
    candidates = [values_root / "sites" / site / "site.yaml", values_root / site / "site.yaml"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise CanonicalValuesError(f"selected canonical site file does not exist: {site}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-file", type=Path, help="canonical site.yaml path")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "infra" / "services.json",
        help="service capability catalog path",
    )
    parser.add_argument("command", choices=("validate", "summary"))
    args = parser.parse_args(argv)
    try:
        site_path = (args.site_file or _default_site_path()).resolve()
        expected_site = os.environ.get("VALUES_SITE") if args.site_file is None else None
        model = load_site(site_path, expected_site=expected_site, catalog_path=args.catalog)
        if args.command == "summary":
            print(json.dumps(redacted_summary(model), sort_keys=True, indent=2))
        else:
            print(f"valid canonical site: {model.site.name} ({site_path})")
            print(f"model_digest: {redacted_summary(model)['model_digest']}")
    except (CanonicalValuesError, OSError) as error:
        print(f"canonical values error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
