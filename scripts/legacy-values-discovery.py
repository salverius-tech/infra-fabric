#!/usr/bin/env python3
"""Report legacy values that require review before canonical migration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from legacy_values_discovery import DiscoveryError, discover_legacy, render_migration_report
except ModuleNotFoundError:  # pragma: no cover - direct import from another cwd
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from legacy_values_discovery import DiscoveryError, discover_legacy, render_migration_report


def _reject_values_output(output: Path, values_dir: Path) -> None:
    resolved_output = output.expanduser().resolve()
    resolved_values = values_dir.expanduser().resolve()
    if resolved_output == resolved_values or resolved_values in resolved_output.parents:
        raise DiscoveryError("report output must be outside the legacy values directory")


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="write the redacted JSON report to this path")
    args = parser.parse_args(argv)
    try:
        payload = render_migration_report(discover_legacy(args.values_dir))
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(encoded, end="")
        else:
            _reject_values_output(args.output, args.values_dir)
            _write_report(args.output, payload)
            print(f"wrote redacted legacy discovery report: {args.output}")
    except (DiscoveryError, OSError, ValueError) as error:
        print(f"legacy discovery failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
