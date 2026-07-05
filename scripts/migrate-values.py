#!/usr/bin/env python3
"""Migrate private values files to the current layout."""
from __future__ import annotations

import argparse
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

SECRET_KEYS = {
    "PROXMOX_VE_API_TOKEN",
    "PROXMOX_VE_PASSWORD",
    "TECHNITIUM_API_TOKEN",
    "TF_VAR_technitium_api_token",
    "CF_DNS_API_TOKEN",
    "FORGEJO_RUNNER_REGISTRATION_SECRET",
    "TAILSCALE_AUTH_KEY",
}

ENV_TO_INVENTORY = {
    "SERVER_NAME": "caddy_server_name",
    "FORGEJO_DOMAIN": "forgejo_domain",
    "FORGEJO_VERSION": "forgejo_version",
    "FORGEJO_SSH_PORT": "forgejo_ssh_port",
    "FORGEJO_ENABLE_CADDY": "forgejo_enable_caddy",
}
HISTORICAL_ENV_KEYS = ("FORGEJO_SERVER_NAME", "FORGEJO_UPSTREAM")

MIGRATION_ENV_KEYS = {
    "TF_VAR_technitium_api_token",
    "TECHNITIUM_API_TOKEN",
    "TECHNITIUM_API_URL",
    "DNS_RECORDS_FILE",
    *ENV_TO_INVENTORY,
    *HISTORICAL_ENV_KEYS,
}

ENV_LINE_RE = re.compile(r"^(?P<prefix>\s*(?:export\s+)?)(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<sep>=)(?P<value>.*)$")
TFVARS_LINE_RE = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*?)(?:\s*#.*)?$")


class MigrationError(ValueError):
    pass


@dataclass
class EnvEntry:
    index: int
    key: str
    value: str


def parse_scalar(raw_value: str) -> str:
    try:
        parts = shlex.split(raw_value, posix=True, comments=False)
    except ValueError as error:
        raise MigrationError(f"invalid quoting: {error}") from error
    if len(parts) != 1:
        raise MigrationError("expected exactly one scalar value")
    return parts[0]


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_env_lines(lines: list[str], path: Path) -> dict[str, EnvEntry]:
    entries: dict[str, EnvEntry] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        if key not in MIGRATION_ENV_KEYS:
            continue
        if key in entries:
            raise MigrationError(f"{path}: duplicate environment key {key}")
        entries[key] = EnvEntry(index, key, parse_scalar(match.group("value")))
    return entries


def set_env(lines: list[str], entries: dict[str, EnvEntry], key: str, value: str) -> bool:
    line = f"export {key}={shell_quote(value)}"
    if key in entries:
        if entries[key].value == value:
            return False
        lines[entries[key].index] = line
        entries[key].value = value
        return True
    if lines and lines[-1].strip():
        lines.append("")
    entries[key] = EnvEntry(len(lines), key, value)
    lines.append(line)
    return True


def remove_env(lines: list[str], entries: dict[str, EnvEntry], key: str) -> bool:
    entry = entries.get(key)
    if entry is None:
        return False
    lines[entry.index] = None  # type: ignore[assignment]
    del entries[key]
    for other in entries.values():
        if other.index > entry.index:
            other.index -= 1
    lines[:] = [line for line in lines if line is not None]
    return True


def parse_tfvars(lines: list[str], path: Path) -> dict[str, tuple[int, str]]:
    values: dict[str, tuple[int, str]] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = TFVARS_LINE_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        if key not in {"technitium_api_url", "dns_records_file"}:
            continue
        if key in values:
            raise MigrationError(f"{path}: duplicate tfvars key {key}")
        values[key] = (index, parse_scalar(match.group("value")))
    return values


def remove_tfvars(lines: list[str], values: dict[str, tuple[int, str]], key: str) -> bool:
    item = values.get(key)
    if item is None:
        return False
    index, _value = item
    lines[index] = None  # type: ignore[assignment]
    del values[key]
    for other_key, (other_index, other_value) in list(values.items()):
        if other_index > index:
            values[other_key] = (other_index - 1, other_value)
    lines[:] = [line for line in lines if line is not None]
    return True


def inventory_has_key(text: str, key: str) -> bool:
    return re.search(rf"(?m)^\s*{re.escape(key)}\s*:", text) is not None


def migrate(values_dir: Path) -> list[str]:
    env_path = values_dir / ".env"
    tfvars_path = values_dir / "terraform.tfvars"
    inventory_path = values_dir / "ansible" / "inventory" / "local.yml"

    changes: list[str] = []
    env_lines = read_lines(env_path)
    tfvars_lines = read_lines(tfvars_path)
    inventory_text = inventory_path.read_text(encoding="utf-8") if inventory_path.exists() else ""

    env_entries = parse_env_lines(env_lines, env_path)
    tfvars_values = parse_tfvars(tfvars_lines, tfvars_path)

    old_token = env_entries.get("TF_VAR_technitium_api_token")
    new_token = env_entries.get("TECHNITIUM_API_TOKEN")
    if old_token and new_token and old_token.value != new_token.value:
        raise MigrationError(
            f"{env_path}: TF_VAR_technitium_api_token and TECHNITIUM_API_TOKEN differ"
        )
    if old_token and not new_token:
        set_env(env_lines, env_entries, "TECHNITIUM_API_TOKEN", old_token.value)
        changes.append("moved TF_VAR_technitium_api_token to TECHNITIUM_API_TOKEN")
    if remove_env(env_lines, env_entries, "TF_VAR_technitium_api_token"):
        changes.append("removed TF_VAR_technitium_api_token")

    old_url = tfvars_values.get("technitium_api_url")
    if old_url and "TECHNITIUM_API_URL" not in env_entries:
        set_env(env_lines, env_entries, "TECHNITIUM_API_URL", old_url[1])
        changes.append("moved technitium_api_url to TECHNITIUM_API_URL")
    if remove_tfvars(tfvars_lines, tfvars_values, "technitium_api_url"):
        changes.append("removed technitium_api_url from terraform.tfvars")

    old_dns_file = tfvars_values.get("dns_records_file")
    if old_dns_file and "DNS_RECORDS_FILE" not in env_entries:
        dns_file = old_dns_file[1]
        if dns_file == "../../values/dns-records.local.json":
            dns_file = "values/dns-records.local.json"
        set_env(env_lines, env_entries, "DNS_RECORDS_FILE", dns_file)
        changes.append("moved dns_records_file to DNS_RECORDS_FILE")
    if remove_tfvars(tfvars_lines, tfvars_values, "dns_records_file"):
        changes.append("removed dns_records_file from terraform.tfvars")

    for env_key, inventory_key in ENV_TO_INVENTORY.items():
        if env_key not in env_entries:
            continue
        if not inventory_has_key(inventory_text, inventory_key):
            key_label = f"{env_key} remains in .env because {inventory_key} is missing"
            changes.append(key_label)
            continue
        if remove_env(env_lines, env_entries, env_key):
            changes.append(f"removed duplicate {env_key}; inventory owns {inventory_key}")

    for env_key in HISTORICAL_ENV_KEYS:
        if remove_env(env_lines, env_entries, env_key):
            changes.append(f"removed historical unused {env_key}")

    if "DNS_RECORDS_FILE" not in env_entries:
        set_env(env_lines, env_entries, "DNS_RECORDS_FILE", "values/dns-records.local.json")
        changes.append("added DNS_RECORDS_FILE default")

    if changes:
        write_lines(env_path, env_lines)
        write_lines(tfvars_path, tfvars_lines)
    return changes


def redact_change(change: str) -> str:
    for key in SECRET_KEYS:
        change = change.replace(key, key)
    return change


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-dir", type=Path, default=Path("values"))
    args = parser.parse_args(argv)

    try:
        changes = migrate(args.values_dir)
    except MigrationError as error:
        print(f"values migration failed: {error}", file=sys.stderr)
        return 1

    if changes:
        print("migrated values:")
        for change in changes:
            print(f"- {redact_change(change)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
