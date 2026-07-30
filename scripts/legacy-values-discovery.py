#!/usr/bin/env python3
"""Report legacy values that require review before canonical migration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from legacy_values_discovery import DiscoveryError, build_candidate_site, discover_legacy, render_migration_report
except ModuleNotFoundError:  # pragma: no cover - direct import from another cwd
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from legacy_values_discovery import DiscoveryError, build_candidate_site, discover_legacy, render_migration_report


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


def _write_candidate(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        with temporary.open("w", encoding="utf-8") as handle:
            yaml.dump(payload, handle)
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-dir", type=Path, required=True)
    parser.add_argument("--repo", type=Path, help="public repository root for bounded Ansible inventory admission")
    parser.add_argument("--ansible-inventory", type=Path, help="opt-in public Ansible inventory source for bounded discovery")
    parser.add_argument("--output", type=Path, help="write the redacted JSON report to this path")
    parser.add_argument("--candidate-base", type=Path, help="approved canonical YAML base for public candidate generation")
    parser.add_argument("--candidate-output", type=Path, help="write a public candidate YAML outside the legacy values directory")
    parser.add_argument("--site", help="override candidate site.name")
    args = parser.parse_args(argv)
    try:
        report = discover_legacy(
            args.values_dir,
            repo=args.repo,
            ansible_inventory=args.ansible_inventory,
        )
        payload = render_migration_report(report)
        if args.candidate_base is not None or args.candidate_output is not None:
            if args.candidate_base is None or args.candidate_output is None:
                raise DiscoveryError("--candidate-base and --candidate-output must be supplied together")
            if args.output is not None:
                raise DiscoveryError("candidate generation cannot be combined with --output")
            _reject_values_output(args.candidate_output, args.values_dir)
            from ruamel.yaml import YAML

            yaml = YAML(typ="safe")
            base = yaml.load(args.candidate_base.read_text(encoding="utf-8"))
            candidate = build_candidate_site(report, base_document=base, site_name=args.site)
            _write_candidate(args.candidate_output, candidate)
            print(f"wrote public canonical candidate: {args.candidate_output}")
            return 0
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
