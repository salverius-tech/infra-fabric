#!/usr/bin/env python3
"""Enforce explicit minimum coverage for mutation-critical modules."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


class CoverageFloorError(ValueError):
    """Raised when the coverage report or floor policy is invalid."""


def check_floors(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    if policy.get("schema_version") != 1 or not isinstance(policy.get("floors"), dict):
        raise CoverageFloorError("coverage floor policy is invalid")
    report_files = report.get("files")
    if not isinstance(report_files, dict):
        raise CoverageFloorError("coverage JSON report is invalid")

    failures: list[str] = []
    for path, floor in sorted(policy["floors"].items()):
        if not isinstance(path, str) or not isinstance(floor, int) or isinstance(floor, bool):
            raise CoverageFloorError("coverage floor entry is invalid")
        result = report_files.get(path)
        if not isinstance(result, dict):
            failures.append(f"{path}: missing from coverage report")
            continue
        summary = result.get("summary")
        percentage = summary.get("percent_covered") if isinstance(summary, dict) else None
        if not isinstance(percentage, (int, float)) or isinstance(percentage, bool):
            failures.append(f"{path}: coverage percentage is missing")
        elif percentage < floor:
            failures.append(f"{path}: {percentage:.1f}% is below the {floor}% floor")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--floors", type=Path, default=Path("tools/coverage-floors.json")
    )
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        policy = json.loads(args.floors.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or not isinstance(policy, dict):
            raise CoverageFloorError("coverage report and policy must be JSON objects")
        failures = check_floors(report, policy)
    except (OSError, json.JSONDecodeError, CoverageFloorError) as error:
        print(f"coverage floor check failed: {error}", file=sys.stderr)
        return 2

    if failures:
        for failure in failures:
            print(f"coverage floor failed: {failure}", file=sys.stderr)
        return 1
    print(f"coverage floors passed for {len(policy['floors'])} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
