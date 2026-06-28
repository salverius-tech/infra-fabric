#!/usr/bin/env python3
"""Parse values/.env as data and emit sanitized shell exports."""
from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

ALLOWED_KEYS = {
    "PROXMOX_VE_ENDPOINT",
    "PROXMOX_VE_API_TOKEN",
    "PROXMOX_VE_USERNAME",
    "PROXMOX_VE_PASSWORD",
    "PVE_HOST",
    "SERVER_NAME",
    "CF_API_EMAIL",
    "CF_DNS_API_TOKEN",
    "TF_VAR_container_root_password",
    "TF_VAR_container_ssh_public_keys",
    "TF_VAR_technitium_api_token",
    "TECHNITIUM_API_TOKEN",
    "TECHNITIUM_ADMIN_USER",
    "TECHNITIUM_ADMIN_PASSWORD",
    "TECHNITIUM_ADMIN_PASS",
    "FORGEJO_VERSION",
    "FORGEJO_DOMAIN",
    "FORGEJO_SERVER_NAME",
    "FORGEJO_UPSTREAM",
    "FORGEJO_SSH_PORT",
    "FORGEJO_ENABLE_CADDY",
}

KEY_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


class EnvError(ValueError):
    pass


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = KEY_RE.match(line)
        if not match:
            raise EnvError(f"{path}:{line_number}: expected KEY=value or export KEY=value")

        key, raw_value = match.groups()
        if key not in ALLOWED_KEYS:
            print(
                f"{path}:{line_number}: ignoring unsupported environment key {key}",
                file=sys.stderr,
            )
            continue
        if key in values:
            raise EnvError(f"{path}:{line_number}: duplicate environment key {key}")
        try:
            parts = shlex.split(raw_value, posix=True)
        except ValueError as error:
            raise EnvError(f"{path}:{line_number}: invalid quoting for {key}: {error}") from error
        if len(parts) != 1:
            raise EnvError(f"{path}:{line_number}: {key} must have exactly one value")
        values[key] = parts[0]
    return values


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keys", action="store_true", help="print parsed keys, one per line")
    parser.add_argument("--env-file", action="store_true", help="print KEY=value lines for docker compose --env-from-file")
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    try:
        values = parse_env(args.path)
    except EnvError as error:
        print(error, file=sys.stderr)
        return 1

    if args.keys:
        for key in values:
            print(key)
    elif args.env_file:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                print(f"{key} contains a newline and cannot be used in an env file", file=sys.stderr)
                return 1
            print(f"{key}={value}")
    else:
        for key, value in values.items():
            print(f"export {key}={shell_quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
