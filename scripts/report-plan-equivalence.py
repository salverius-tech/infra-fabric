#!/usr/bin/env python3
"""Report semantic equivalence for two saved OpenTofu JSON plans."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_equivalence import PlanEquivalenceError, compare_plans
from tofu_plan_equivalence import normalize_tofu_plan


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON plan: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON plan must be an object: {path.name}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="saved tofu show -json output before migration")
    parser.add_argument("after", type=Path, help="saved tofu show -json output after migration")
    args = parser.parse_args(argv)
    try:
        result = compare_plans(normalize_tofu_plan(_load(args.before)), normalize_tofu_plan(_load(args.after)))
    except (OSError, PlanEquivalenceError, ValueError) as error:
        print(json.dumps({"equivalent": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["equivalent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
