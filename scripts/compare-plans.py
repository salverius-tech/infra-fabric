#!/usr/bin/env python3
"""Compare two OpenTofu/Terraform JSON plans semantically."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plan_equivalence import PlanEquivalenceError, compare_plans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_plans(args.before, args.after)
    except PlanEquivalenceError as error:
        print(f"plan equivalence comparison failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["equivalent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
