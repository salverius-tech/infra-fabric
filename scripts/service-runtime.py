#!/usr/bin/env python3
"""Print the configured runtime type for an enabled service."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_catalog import ServiceCatalogError, load_catalog
CATALOG_PATH = Path(__file__).resolve().parents[1] / "infra" / "services.json"


class ServiceRuntimeError(ValueError):
    pass


def load_projection(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ServiceRuntimeError(f"cannot read canonical projection {path}: {error}") from error
    if not isinstance(data, dict):
        raise ServiceRuntimeError(f"canonical projection {path} must contain an object")
    return data


def runtime_type(service: str, tfvars: dict[str, Any]) -> str:
    retired_alias = f"{service}_runtime"
    if retired_alias in tfvars:
        raise ServiceRuntimeError(f"retired runtime alias is not accepted: {retired_alias}; use service_runtime.{service}")
    runtimes = tfvars.get("service_runtime", {})
    runtime = runtimes.get(service) if isinstance(runtimes, dict) else None
    if not isinstance(runtime, dict):
        runtime = {}
    try:
        metadata = load_catalog(CATALOG_PATH).get(service).runtime
    except ServiceCatalogError as error:
        raise ServiceRuntimeError(f"unknown runtime service: {service}") from error
    if metadata is None:
        raise ServiceRuntimeError(f"service does not own a runtime: {service}")
    selected = runtime.get("type", metadata.default_type)
    if selected not in metadata.supported_types:
        raise ServiceRuntimeError(f"unsupported runtime for {service}: {selected}")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service")
    parser.add_argument("--projection", type=Path, required=True, help="generated canonical OpenTofu JSON projection")
    args = parser.parse_args(argv)
    try:
        projection = load_projection(args.projection)
        enabled = projection.get("enabled_services")
        if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
            raise ServiceRuntimeError("canonical projection enabled_services must be a string list")
        runtimes = projection.get("service_runtime")
        if not isinstance(runtimes, dict):
            raise ServiceRuntimeError("canonical projection service_runtime must be an object")
        tfvars = projection
        if args.service not in enabled:
            raise ServiceRuntimeError(f"service is not enabled: {args.service}")
        if not isinstance(runtimes.get(args.service), dict):
            raise ServiceRuntimeError(
                f"canonical projection service_runtime.{args.service} must be an object"
            )
        print(runtime_type(args.service, tfvars))
    except ServiceRuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
