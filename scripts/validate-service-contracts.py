#!/usr/bin/env python3
"""Validate every public service catalog entry without mutating the repository."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

SERVICE_AUTHOR = Path(__file__).resolve().with_name("service-author.py")
SPEC = importlib.util.spec_from_file_location("service_author", SERVICE_AUTHOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, help="write a deterministic JSON report")
    args = parser.parse_args(argv)
    try:
        report = MODULE.build_catalog_report(args.repo)
    except (OSError, ValueError) as exc:
        print(f"service-contracts: {exc}", file=sys.stderr)
        return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if report["summary"]["failed"]:
        for service in report["services"]:
            for error in service["errors"]:
                print(f"service-contracts: {service['service_id']}: {error}", file=sys.stderr)
        return 1
    print(f"validated all public service catalog contracts ({report['summary']['total']} services)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())