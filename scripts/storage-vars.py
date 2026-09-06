#!/usr/bin/env python3
"""Emit Ansible vars for host storage that must exist before OpenTofu apply."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

class StorageVarsError(ValueError):
    pass


def load_projection(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StorageVarsError(f"cannot read canonical projection {path}: {error}") from error
    if not isinstance(data, dict):
        raise StorageVarsError(f"canonical projection {path} must contain an object")
    return data


def storage_definitions(tfvars: dict[str, Any], service: str) -> dict[str, dict[str, Any]]:
    storage = tfvars.get("service_storage", {})
    if isinstance(storage, dict) and isinstance(storage.get(service), dict):
        return {
            mount_name: definition
            for mount_name, definition in storage[service].items()
            if isinstance(definition, dict)
        }
    return {}


def build_storage_mounts(enabled_services: list[str], tfvars: dict[str, Any]) -> list[dict[str, Any]]:
    mounts: list[dict[str, Any]] = []
    for service in enabled_services:
        for mount_name, definition in storage_definitions(tfvars, service).items():
            if definition.get("type") != "bind":
                continue
            source = definition.get("source")
            if not source:
                raise StorageVarsError(f"missing bind source for {service}.{mount_name}")
            host_prepare = definition.get("host_prepare")
            if not isinstance(host_prepare, dict):
                host_prepare = {"type": "directory" if definition.get("create_source", True) else "none"}
            if host_prepare.get("type", "directory") == "none":
                continue
            mounts.append(
                {
                    "name": service,
                    "mount": mount_name,
                    "source": source,
                    "target": definition.get("target", ""),
                    "uid": definition.get("host_uid", 100000),
                    "gid": definition.get("host_gid", 100000),
                    "mode": definition.get("mode", "0750"),
                    "host_prepare": host_prepare,
                }
            )
    return mounts


def format_storage_summary(mounts: list[dict[str, Any]]) -> str:
    lines = ["Storage prep summary:"]
    if not mounts:
        lines.append("  none")
        return "\n".join(lines)
    for mount in mounts:
        lines.append(
            "  {name}.{mount}: {prepare} source={source} target={target} uid={uid} gid={gid} mode={mode}".format(
                name=mount["name"],
                mount=mount["mount"],
                prepare=mount["host_prepare"].get("type", "directory"),
                source=mount["source"],
                target=mount["target"],
                uid=mount["uid"],
                gid=mount["gid"],
                mode=mount["mode"],
            )
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", type=Path, required=True, help="generated canonical OpenTofu JSON projection")
    parser.add_argument("--service", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        projection = load_projection(args.projection)
        enabled_services = projection.get("enabled_services")
        if not isinstance(enabled_services, list) or not all(isinstance(service, str) for service in enabled_services):
            raise StorageVarsError("canonical projection enabled_services must be a string list")
        storage = projection.get("service_storage")
        if not isinstance(storage, dict):
            raise StorageVarsError("canonical projection service_storage must be an object")
        if any(service in storage and not isinstance(storage[service], dict) for service in enabled_services):
            raise StorageVarsError("canonical projection service_storage entries must be objects")
        tfvars = projection
        if args.service:
            if args.service not in enabled_services:
                raise StorageVarsError(f"service is not enabled: {args.service}")
            enabled_services = [args.service]
        mounts = build_storage_mounts(enabled_services, tfvars)
        payload = {"storage_bind_mounts": mounts}
    except (StorageVarsError, OSError) as error:
        print(f"storage vars failed: {error}", file=sys.stderr)
        return 1
    if args.summary:
        print(format_storage_summary(mounts))
    else:
        print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
