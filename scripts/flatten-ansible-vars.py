#!/usr/bin/env python3
"""Flatten canonical Ansible adapter variables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def flatten(projection: dict[str, Any]) -> dict[str, Any]:
    services = projection.get("services")
    if not isinstance(services, dict):
        raise ValueError("canonical Ansible vars projection has an invalid shape")
    flattened = {key: value for key, value in projection.items() if key != "services"}
    for service, values in sorted(services.items()):
        if not isinstance(values, dict) or not isinstance(values.get("ansible_vars"), dict):
            raise ValueError(f"canonical Ansible adapter vars are invalid: {service}")
        for key, value in values["ansible_vars"].items():
            if not isinstance(key, str):
                raise ValueError(f"canonical Ansible adapter key is invalid: {service}")
            if key in flattened and flattened[key] != value:
                raise ValueError(f"conflicting canonical Ansible adapter variable: {key}")
            flattened[key] = value
    return flattened


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    projection = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.write_text(json.dumps(flatten(projection), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
