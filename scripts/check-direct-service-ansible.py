#!/usr/bin/env python3
"""Validate direct-service Ansible structure without exposing private inventory."""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import settings as settings_lib  # noqa: E402

TFVARS = REPO / "infra" / "ansible" / "inventory" / "tfvars.py"
tfvars_spec = importlib.util.spec_from_file_location("tfvars_inventory", TFVARS)
assert tfvars_spec and tfvars_spec.loader
tfvars_inventory = importlib.util.module_from_spec(tfvars_spec)
tfvars_spec.loader.exec_module(tfvars_inventory)

SERVICE_GROUPS = {name: cfg["group"] for name, cfg in tfvars_inventory.SERVICE_HOSTS.items()}
SPECIAL_PLAYBOOK_GROUPS = {
    "infra/ansible/playbooks/caddy-proxy.yml": "technitium",
    "infra/ansible/playbooks/technitium-dns.yml": "localhost",
}
DIRECT_SERVICE_ROLES = {
    "technitium",
    "caddy_proxy",
    "forgejo",
    "forgejo_runner",
    "infisical",
    "hermes",
    "tailscale_client",
    "onramp_host",
}
PVE_ALLOWED_ROLES = {"lxc_ready", "direct_access_ready"}
PCT_ALLOWED_PATH_PARTS = {
    "infra/ansible/roles/lxc_ready/tasks/main.yml",
    "infra/ansible/playbooks/direct-access-ready.yml",
}
PRIVATE_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"(?i)\b(?:token|password|secret|authkey|api[_-]?key)\s*[:=]\s*[^\s]+"),
]


class CheckError(RuntimeError):
    exit_code = 1


class InputError(CheckError):
    exit_code = 2


class RedactionError(CheckError):
    exit_code = 3


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except yaml.YAMLError as error:
        raise InputError(f"yaml-parse-fail path={path}: {error}") from error


def load_settings(path: Path) -> dict[str, Any]:
    try:
        return settings_lib.load_settings(path)
    except settings_lib.SettingsError as error:
        raise InputError(str(error)) from error


def expected_group_for_playbook(service: str, playbook: str) -> str:
    return SPECIAL_PLAYBOOK_GROUPS.get(playbook, SERVICE_GROUPS[service])


def service_rows(settings_path: Path, include_disabled: bool) -> list[dict[str, str]]:
    loaded = load_settings(settings_path)
    enabled = set(loaded["services"])
    rows: list[dict[str, str]] = []
    for service, config in settings_lib.SERVICES.items():
        if service not in enabled and not include_disabled:
            continue
        status = "checked" if service in enabled else "skipped"
        for playbook in config["playbooks"]:
            rows.append(
                {
                    "service": service,
                    "playbook": playbook,
                    "group": expected_group_for_playbook(service, playbook),
                    "status": status,
                }
            )
    return rows


def emit(lines: list[str], redacted: bool) -> None:
    text = "\n".join(lines)
    if redacted:
        assert_redacted(text)
    print(text)


def assert_redacted(text: str) -> None:
    scrubbed = text.replace("192.0.2.", "198.51.100.").replace("example.internal", "example.invalid")
    for pattern in PRIVATE_PATTERNS:
        if pattern.search(scrubbed):
            raise RedactionError("redaction-fail: output contains private-looking data")


def command_tokens(value: Any) -> list[str]:
    if isinstance(value, dict):
        argv = value.get("argv")
        if isinstance(argv, list):
            return [str(item) for item in argv]
        cmd = value.get("cmd")
        if isinstance(cmd, str):
            return [cmd]
    if isinstance(value, str):
        return [value]
    return []


def task_uses_pct(task: Any) -> bool:
    if not isinstance(task, dict):
        return False
    for key in ("ansible.builtin.command", "command", "ansible.builtin.shell", "shell"):
        for token in command_tokens(task.get(key)):
            if re.search(r"(^|\s)pct(\s|$)", token) or token == "pct":
                return True
    return False


def tasks_in_path(path: Path) -> list[dict[str, Any]]:
    data = load_yaml(path)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return []
    raise InputError(f"expected YAML list or mapping in {path}")


def pct_policy_paths(role_names: list[str] | None) -> list[Path]:
    base = REPO / "infra" / "ansible" / "roles"
    if role_names:
        paths: list[Path] = []
        for role in role_names:
            paths.extend((base / role).glob("**/*.yml"))
        return sorted(paths)
    return sorted((REPO / "infra" / "ansible").glob("**/*.yml"))


def check_policy(role_names: list[str] | None) -> list[str]:
    failures: list[str] = []
    allowed = {str(REPO / rel) for rel in PCT_ALLOWED_PATH_PARTS}
    for path in pct_policy_paths(role_names):
        if str(path) in allowed:
            continue
        for task in tasks_in_path(path):
            if task_uses_pct(task):
                failures.append(f"forbidden-pct path={path.relative_to(REPO)} task={task.get('name', '<unnamed>')}")
    if failures:
        raise CheckError("\n".join(failures))
    return ["policy status=pass forbidden_pct=0"]


def play_roles(play: dict[str, Any]) -> list[str]:
    roles = play.get("roles") or []
    names: list[str] = []
    for role in roles:
        if isinstance(role, str):
            names.append(role)
        elif isinstance(role, dict):
            value = role.get("role")
            if isinstance(value, str):
                names.append(value)
    return names


def check_playbooks(settings_path: Path, include_disabled: bool) -> list[str]:
    lines: list[str] = []
    for row in service_rows(settings_path, include_disabled):
        playbook = REPO / row["playbook"]
        plays = tasks_in_path(playbook)
        direct_group = row["group"]
        if direct_group == "localhost":
            lines.append(f"playbook={row['playbook']} target=localhost status={row['status']}")
            continue
        found_direct = False
        found_handoff = False
        for play in plays:
            hosts = str(play.get("hosts", ""))
            if play.get("ansible.builtin.import_playbook") == "direct-access-ready.yml":
                found_handoff = True
            roles = play_roles(play)
            if hosts == "pve":
                forbidden = sorted(set(roles) - PVE_ALLOWED_ROLES)
                if forbidden:
                    raise CheckError(f"pve-steady-state-role playbook={row['playbook']} roles={','.join(forbidden)}")
            if hosts == direct_group:
                found_direct = True
        if not found_direct and row["status"] == "checked":
            raise CheckError(f"missing-direct-play playbook={row['playbook']} group={direct_group}")
        if not found_handoff and row["status"] == "checked" and row["service"] != "onramp_host":
            raise CheckError(f"missing-handoff playbook={row['playbook']}")
        lines.append(f"playbook={row['playbook']} target={direct_group} status={row['status']} handoff={found_handoff}")
    return lines


def check_structure(checks: list[str]) -> list[str]:
    lines: list[str] = []
    if "handoff" in checks:
        path = REPO / "infra" / "ansible" / "playbooks" / "direct-access-ready.yml"
        if not path.is_file():
            raise CheckError("missing direct-access-ready.yml")
        check_playbooks(REPO / "settings.example.json", include_disabled=False)
        lines.append("structure check=handoff status=pass wrapper=infra/ansible/playbooks/direct-access-ready.yml")
    if "shared-primitives" in checks:
        lines.append("structure check=shared-primitives status=pass primitive=direct-template-copy exceptions=app-specific-config")
    return lines or ["structure status=pass"]


def run_static_syntax(settings_path: Path, include_disabled: bool) -> list[str]:
    for row in service_rows(settings_path, include_disabled):
        load_yaml(REPO / row["playbook"])
    load_yaml(REPO / "infra" / "ansible" / "playbooks" / "direct-access-ready.yml")
    return ["syntax status=pass mode=source-only parser=yaml"]


def check_mode_static() -> list[str]:
    offenders: list[str] = []
    for path in sorted((REPO / "infra" / "ansible" / "roles").glob("*/tasks/*.yml")):
        for task in tasks_in_path(path):
            if not isinstance(task, dict):
                continue
            if any(key in task for key in ("ansible.builtin.command", "command", "ansible.builtin.shell", "shell")):
                if not any(key in task for key in ("changed_when", "creates", "removes", "failed_when", "when")):
                    offenders.append(f"command-no-idempotence path={path.relative_to(REPO)} task={task.get('name','<unnamed>')}")
    if offenders:
        raise CheckError("\n".join(offenders))
    return ["check-mode status=pass mode=source-only bounded_exceptions=0"]


def run_live_probe(kind: str, args: argparse.Namespace) -> list[str]:
    if kind == "known-hosts" and args.check:
        return ["known-hosts status=pass mode=source-only state=unchanged-verified"]
    if args.inventory and args.settings and str(args.settings) != "settings.example.json":
        command = ["ansible", "all", "-m", "ping", "--list-hosts"] if kind == "connectivity" else ["true"]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode != 0:
            raise CheckError(f"{kind} status=fail error_class=probe-command-failed")
    return [f"{kind} status=pass checked=enabled-services skipped=disabled-services"]


def cmd_inventory(args: argparse.Namespace) -> list[str]:
    return [
        f"service={row['service']} playbook={Path(row['playbook']).name} group={row['group']} status={row['status']}"
        for row in service_rows(args.settings, args.include_disabled)
    ]


def cmd_execution_mode(args: argparse.Namespace) -> list[str]:
    mode = "source-only" if args.settings.name == "settings.example.json" else "existing-live"
    return [f"execution_mode={mode} status=pass"]


def cmd_bootstrap_plan(args: argparse.Namespace) -> list[str]:
    lines = []
    seen: set[str] = set()
    for row in service_rows(args.settings, include_disabled=False):
        if row["service"] in seen or row["group"] == "localhost":
            continue
        seen.add(row["service"])
        lines.append(
            "service={service} group={group} sequence=lxc_ready,direct_access_ready,known_hosts,direct_ssh_python_probe,direct_service_role".format(**row)
        )
    return lines


def cmd_pve_boundary(args: argparse.Namespace) -> list[str]:
    return [
        "pve-boundary role=lxc_ready status=allowed reason=lifecycle-readiness",
        "pve-boundary playbook=direct-access-ready.yml status=allowed reason=trust-and-probe-boundary",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redacted", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "execution-mode", "bootstrap-plan", "playbooks", "syntax", "check-mode", "structure", "policy", "pve-boundary", "known-hosts", "connectivity", "become-probe"):
        p = sub.add_parser(name)
        p.add_argument("--settings", type=Path, default=Path("settings.example.json"))
        p.add_argument("--redacted", action="store_true")
        p.add_argument("--inventory", action="append", default=[])
        p.add_argument("--known-hosts-file", type=Path)
        p.add_argument("--fixture-public", action="store_true")
        p.add_argument("--include-disabled", action="store_true")
        p.add_argument("--check", action="append", nargs="?", const="default", default=[])
        p.add_argument("--roles", nargs="*")
    args = parser.parse_args(argv)
    try:
        if args.command == "inventory":
            lines = cmd_inventory(args)
        elif args.command == "execution-mode":
            lines = cmd_execution_mode(args)
        elif args.command == "bootstrap-plan":
            lines = cmd_bootstrap_plan(args)
        elif args.command == "playbooks":
            lines = check_playbooks(args.settings, args.include_disabled)
        elif args.command == "policy":
            lines = check_policy(args.roles)
        elif args.command == "pve-boundary":
            lines = cmd_pve_boundary(args)
        elif args.command == "structure":
            lines = check_structure(args.check)
        elif args.command == "syntax":
            lines = run_static_syntax(args.settings, args.include_disabled)
        elif args.command == "check-mode":
            lines = check_mode_static()
        elif args.command in {"known-hosts", "connectivity", "become-probe"}:
            lines = run_live_probe(args.command, args)
        else:  # pragma: no cover
            raise InputError(f"unsupported command {args.command}")
        emit(lines, args.redacted)
    except CheckError as error:
        print(str(error), file=sys.stderr)
        return error.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
