#!/usr/bin/env python3
"""Run safe, repo-native Hermes operator actions with sanitized output."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from canonical_values import CanonicalValuesError, load_site

SCHEMA_VERSION = 3
MAX_OUTPUT = 6000
PRIVATE_IP_RE = re.compile(
    r"(?<![0-9.])(?:10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|"
    r"172\.(?:1[6-9]|2[0-9]|3[0-1])\.[0-9]{1,3}\.[0-9]{1,3}|"
    r"192\.168\.[0-9]{1,3}\.[0-9]{1,3})(?![0-9.])"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b[A-Z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|PASS)[A-Z0-9_]*\s*[=:]\s*[^\s]+"
)
PRIVATE_PATH_RE = re.compile(r"(?:/workspace/)?values/[^\s]+")
HOSTNAME_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:[A-Za-z0-9-]+\.)+(?:internal|local|lan|net|com|org)(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)


class OperatorError(RuntimeError):
    pass


def redact_output(text: str, secret_values: set[str] | None = None) -> str:
    """Remove known secret values and private-looking data before returning output."""
    redacted = text
    for value in sorted(secret_values or set(), key=len, reverse=True):
        if value:
            redacted = redacted.replace(value, "<redacted>")
    redacted = SECRET_ASSIGNMENT_RE.sub("<redacted-assignment>", redacted)
    redacted = PRIVATE_IP_RE.sub("<private-ip>", redacted)
    redacted = HOSTNAME_RE.sub("<private-host>", redacted)
    redacted = PRIVATE_PATH_RE.sub("values/<redacted>", redacted)
    if len(redacted) > MAX_OUTPUT:
        redacted = redacted[:MAX_OUTPUT] + "\n<output-truncated>"
    return redacted


def load_registry(repo: Path) -> dict[str, Any]:
    path = repo / "infra" / "services.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OperatorError(f"cannot read service registry: {path}") from error
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        raise OperatorError("service registry is invalid")
    return data


def enabled_services(repo: Path) -> list[str]:
    registry = load_registry(repo)
    selected_site = os.environ.get("VALUES_SITE", "")
    canonical_path = repo / "values" / "sites" / selected_site / "site.yaml" if selected_site else None
    if canonical_path is not None:
        if not canonical_path.is_file():
            raise OperatorError(f"selected canonical site is missing: {selected_site}")
        try:
            model = load_site(canonical_path, expected_site=selected_site, catalog_path=repo / "infra" / "services.json")
        except CanonicalValuesError as error:
            raise OperatorError(f"selected canonical site is invalid: {error}") from error
        return sorted(name for name, service in model.services.items() if service.enabled)
    settings_path = repo / "settings.local.json"
    raw: dict[str, Any] = {}
    if settings_path.is_file():
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise OperatorError("operator settings are invalid") from error
    services = raw.get("services", registry.get("default_services", []))
    if not isinstance(services, list) or not all(isinstance(item, str) for item in services):
        raise OperatorError("operator settings services must be a list")
    known = set(registry["services"])
    unknown = sorted(set(services) - known)
    if unknown:
        raise OperatorError(f"operator settings contain unknown services: {', '.join(unknown)}")
    return services


def load_plan_summary(repo: Path) -> dict[str, Any] | None:
    path = repo / "tfplan.meta.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise OperatorError("saved plan metadata is invalid; run just plan again") from error
    if data.get("schema_version") != SCHEMA_VERSION or not isinstance(data.get("summary"), dict):
        raise OperatorError("saved plan metadata is unsupported; run just plan again")
    return data["summary"]


def git_dirty(repo: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return bool(result.stdout.strip())


def status(repo: Path) -> dict[str, Any]:
    """Return only safe operator state, never private values or inventory."""
    plan = load_plan_summary(repo)
    return {
        "action": "status",
        "repository": repo.name,
        "git_dirty": git_dirty(repo),
        "enabled_services": enabled_services(repo),
        "values_configured": (repo / "values").is_dir(),
        "saved_plan": {
            "present": plan is not None,
            "destructive": bool(plan and plan.get("destructive")),
            "resource_changes": plan.get("resource_changes", {}) if plan else {},
        },
    }


def verify_audit(repo: Path) -> dict[str, Any]:
    """Verify the private operator journal and return only safe metadata."""
    head_hash, record_count = read_audit_chain(audit_path(repo))
    return {
        "action": "audit-verify",
        "ok": True,
        "record_count": record_count,
        "head_hash": head_hash,
    }


def audit_path(repo: Path) -> Path:
    configured = os.environ.get("HERMES_OPERATOR_AUDIT_PATH", "")
    return Path(configured).expanduser() if configured else repo / ".tmp" / "hermes-operator-audit.jsonl"


def audit_record_hash(record: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "record_hash"}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_audit_chain(path: Path, *, allow_missing: bool = False) -> tuple[str, int]:
    if not path.exists():
        if not allow_missing:
            raise OperatorError("Hermes operator audit journal is unavailable")
        return "0" * 64, 0
    previous_hash = "0" * 64
    count = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise OperatorError("cannot read Hermes operator audit journal") from error
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise OperatorError("Hermes operator audit journal is malformed") from error
        if not isinstance(record, dict) or record.get("previous_hash") != previous_hash:
            raise OperatorError("Hermes operator audit journal failed chain verification")
        if record.get("record_hash") != audit_record_hash(record):
            raise OperatorError("Hermes operator audit journal failed integrity verification")
        previous_hash = record["record_hash"]
        count += 1
    return previous_hash, count


@contextlib.contextmanager
def audit_writer_lock(path: Path):
    lock_path = path.with_suffix(".lock")
    try:
        fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.chmod(lock_path, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError as error:
        raise OperatorError("cannot lock Hermes operator audit journal") from error


def write_audit_record(repo: Path, action: str, returncode: int, result: dict[str, Any]) -> None:
    path = audit_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    with audit_writer_lock(path):
        previous_hash, _ = read_audit_chain(path, allow_missing=True)
        summary = result.get("plan") if isinstance(result.get("plan"), dict) else None
        record = {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "action": action,
            "returncode": returncode,
            "ok": returncode == 0,
            "plan": {
                "destructive": bool(summary and summary.get("destructive")),
                "resource_changes": summary.get("resource_changes", {}) if summary else {},
            },
            "previous_hash": previous_hash,
        }
        record["record_hash"] = audit_record_hash(record)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(path, 0o600)
        except OSError as error:
            raise OperatorError("cannot durably append Hermes operator audit record") from error


def default_runner(command: list[str], env: dict[str, str], repo: Path) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, result.stdout


def run_action(
    repo: Path,
    action: str,
    *,
    approve: bool = False,
    allow_destructive: bool = False,
    allow_stateful_batch: bool = False,
    runner: Callable[[list[str], dict[str, str], Path], tuple[int, str] | int] = default_runner,
) -> dict[str, Any]:
    if action not in {"validate", "plan", "apply"}:
        raise OperatorError(f"unsupported operator action: {action}")
    if action == "apply":
        if not approve:
            raise OperatorError("apply requires explicit approval via --approve")
        summary = load_plan_summary(repo)
        if summary is None:
            raise OperatorError("apply requires a saved plan; run just plan first")
        if summary.get("destructive") and not allow_destructive:
            raise OperatorError("destructive apply requires --allow-destructive")
        if len(summary.get("stateful_targets", [])) > 1 and not allow_stateful_batch:
            raise OperatorError("multi-service stateful apply requires --allow-stateful-batch")

    env = dict(os.environ)
    if allow_destructive:
        env["INFRA_ALLOW_DESTROY"] = "1"
    if allow_stateful_batch:
        env["INFRA_ALLOW_STATEFUL_BATCH"] = "1"
    command = ["just", action]
    result = runner(command, env, repo)
    if isinstance(result, tuple):
        returncode, output = result
    else:
        returncode, output = result, ""
    safe_output = redact_output(output)
    response: dict[str, Any] = {
        "action": action,
        "returncode": returncode,
        "ok": returncode == 0,
        "output": safe_output,
    }
    if action in {"plan", "apply"} and (repo / "tfplan.meta.json").is_file():
        response["plan"] = load_plan_summary(repo)
    write_audit_record(repo, action, returncode, response)
    return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "audit-verify", "validate", "plan", "apply"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--approve", action="store_true", help="explicitly approve apply")
    parser.add_argument("--allow-destructive", action="store_true")
    parser.add_argument("--allow-stateful-batch", action="store_true")
    args = parser.parse_args(argv)
    try:
        repo = args.repo.resolve()
        if args.action == "status":
            result = status(repo)
        elif args.action == "audit-verify":
            result = verify_audit(repo)
        else:
            result = run_action(
                repo,
                args.action,
                approve=args.approve,
                allow_destructive=args.allow_destructive,
                allow_stateful_batch=args.allow_stateful_batch,
            )
    except OperatorError as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
