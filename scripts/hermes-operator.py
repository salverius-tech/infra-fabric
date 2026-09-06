#!/usr/bin/env python3
"""Run safe, repo-native Hermes operator actions with sanitized output."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from hermes_audit_chain import (
    AuditChainError,
    audit_record_hash,
    read_audit_chain,  # noqa: F401 - compatibility export used by snapshot/tests
    read_audit_records,
    read_audit_stream,
    validate_audit_lifecycles,
)
from private_files import PrivateFileError, _fsync_descriptor, _private_directory_fd

# Controller-only dependencies are loaded only by actions that need them. The
# deployed read-only bundle intentionally carries neither canonical values nor
# snapshot code; status/audit-verify use only their allow-listed context/audit
# journal inputs. These public symbols preserve testable controller boundaries.
load_site = None


class AuditSnapshotError(RuntimeError):
    """Compatibility boundary for controller-only audit snapshots."""


def create_snapshot(*args: Any, **kwargs: Any) -> Any:
    from hermes_audit_snapshot import AuditSnapshotError as implementation_error
    from hermes_audit_snapshot import create_snapshot as implementation

    try:
        return implementation(*args, **kwargs)
    except implementation_error as error:
        raise AuditSnapshotError(str(error)) from error


def verify_snapshot(*args: Any, **kwargs: Any) -> Any:
    from hermes_audit_snapshot import AuditSnapshotError as implementation_error
    from hermes_audit_snapshot import verify_snapshot as implementation

    try:
        return implementation(*args, **kwargs)
    except implementation_error as error:
        raise AuditSnapshotError(str(error)) from error

# Keep this aligned with scripts/tfplan-metadata.py, the canonical saved-plan
# producer and verifier consumed by the operator bridge.
SCHEMA_VERSION = 7
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
    def __init__(self, message: str, *, correlation_id: str | None = None):
        super().__init__(message)
        self.correlation_id = correlation_id


def mutation_enabled() -> bool:
    """Return the source-controlled pilot mutation gate.

    No configuration or environment value may override this until a trusted
    sender/principal boundary is accepted in a later reviewed source change.
    """
    return False


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


def deployed_context() -> list[str] | None:
    """Load the fixed non-secret context installed with the read-only bridge."""
    path_value = os.environ.get("HERMES_OPERATOR_CONTEXT_PATH", "").strip()
    if not path_value:
        return None
    try:
        payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OperatorError("deployed Hermes operator context is unavailable") from error
    selected_site = os.environ.get("VALUES_SITE", "").strip()
    services = payload.get("enabled_services") if isinstance(payload, dict) else None
    if payload.get("site") != selected_site:
        raise OperatorError("deployed Hermes operator context site does not match VALUES_SITE")
    if (
        not isinstance(services, list)
        or not all(isinstance(service, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", service) for service in services)
        or len(services) != len(set(services))
    ):
        raise OperatorError("deployed Hermes operator context services are unsafe")
    return sorted(services)


def enabled_services(repo: Path) -> list[str]:
    deployed = deployed_context()
    if deployed is not None:
        return deployed
    load_registry(repo)
    selected_site = os.environ.get("VALUES_SITE", "")
    if not selected_site:
        raise OperatorError("VALUES_SITE is required for Hermes operator actions")
    canonical_path = repo / "values" / "sites" / selected_site / "site.yaml"
    if not canonical_path.is_file():
        raise OperatorError(f"selected canonical site is missing: {selected_site}")
    try:
        loader = load_site
        if loader is None:
            from canonical_values import load_site as loader
        model = loader(
            canonical_path,
            expected_site=selected_site,
            catalog_path=repo / "infra" / "services.json",
        )
    except Exception as error:
        raise OperatorError(
            f"selected canonical site is invalid: {error}"
        ) from error
    return sorted(name for name, service in model.services.items() if service.enabled)


def plan_metadata_path(repo: Path) -> Path:
    """Resolve saved-plan metadata from the selected canonical site context."""
    try:
        from values_context import ValuesContextError, from_environment

        context = from_environment(repo)
    except Exception as error:
        raise OperatorError(str(error)) from error
    return (
        context.values_dir / "tfplan.meta.json"
        if context.site
        else repo / "tfplan.meta.json"
    )


def load_plan_summary(repo: Path) -> dict[str, Any] | None:
    path = plan_metadata_path(repo)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise OperatorError(
            "saved plan metadata is invalid; run just plan again"
        ) from error
    if data.get("schema_version") != SCHEMA_VERSION or not isinstance(
        data.get("summary"), dict
    ):
        raise OperatorError("saved plan metadata is unsupported; run just plan again")
    summary = data["summary"]
    counts = summary.get("resource_changes")
    displayed_counts = {"create", "update", "replace", "delete"}
    canonical_counts = displayed_counts | {"read", "no_op"}
    if (
        not isinstance(counts, dict)
        or set(counts) != canonical_counts
        or any(
            isinstance(counts[key], bool)
            or not isinstance(counts[key], int)
            or counts[key] < 0
            for key in canonical_counts
        )
        or not isinstance(summary.get("destructive"), bool)
    ):
        raise OperatorError("saved plan metadata is unsafe; run just plan again")
    stateful_targets = summary.get("stateful_targets", [])
    if not isinstance(stateful_targets, list) or any(
        not isinstance(target, str)
        or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", target)
        for target in stateful_targets
    ):
        raise OperatorError("saved plan metadata is unsafe; run just plan again")
    return {
        "resource_changes": {key: counts[key] for key in sorted(displayed_counts)},
        "destructive": summary["destructive"],
        "stateful_targets": list(stateful_targets),
    }


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
    deployed = deployed_context() is not None
    plan = None if deployed else load_plan_summary(repo)
    return {
        "action": "status",
        "repository": repo.name,
        "git_dirty": git_dirty(repo),
        "enabled_services": enabled_services(repo),
        "values_configured": deployed or (repo / "values").is_dir(),
        "canonical_context": "deployed-projection" if deployed else "selected-site",
        "saved_plan": {
            "present": plan is not None,
            "destructive": bool(plan and plan.get("destructive")),
            "resource_changes": plan.get("resource_changes", {}) if plan else {},
        },
    }


def verify_audit(repo: Path) -> dict[str, Any]:
    """Verify private journal integrity and one-intent/one-terminal lifecycles."""
    try:
        head_hash, records = read_audit_records(audit_path(repo))
        unresolved = validate_audit_lifecycles(records)
    except AuditChainError as error:
        raise OperatorError(str(error)) from error
    return {
        "action": "audit-verify",
        "ok": not unresolved,
        "record_count": len(records),
        "head_hash": head_hash,
        "unresolved_correlations": unresolved,
    }


def audit_path(repo: Path) -> Path:
    configured = os.environ.get("HERMES_OPERATOR_AUDIT_PATH", "")
    return (
        Path(configured).expanduser()
        if configured
        else repo / ".tmp" / "hermes-operator-audit.jsonl"
    )


def audit_backup_dir() -> Path:
    configured = os.environ.get("HERMES_OPERATOR_AUDIT_BACKUP_DIR", "").strip()
    if not configured:
        raise OperatorError(
            "apply requires HERMES_OPERATOR_AUDIT_BACKUP_DIR for pre-execution durability"
        )
    destination = Path(configured).expanduser()
    if not destination.is_absolute():
        raise OperatorError("Hermes operator audit backup directory must be absolute")
    return destination


@contextlib.contextmanager
def audit_writer_lock(path: Path):
    """Hold one no-follow audit parent through lock, chain read, and append."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        with _private_directory_fd(
            path.parent, create=True, private_final=True
        ) as parent_fd:
            lock_name = path.with_suffix(".lock").name
            created_lock = False
            try:
                lock_fd = os.open(
                    lock_name,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow,
                    0o600,
                    dir_fd=parent_fd,
                )
                created_lock = True
            except FileExistsError:
                lock_fd = os.open(lock_name, os.O_RDWR | nofollow, dir_fd=parent_fd)
            try:
                if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                    raise OSError("audit lock is not a regular file")
                os.fchmod(lock_fd, 0o600)
                if created_lock:
                    _fsync_descriptor(parent_fd)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                try:
                    yield parent_fd, created_lock
                finally:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
    except (OSError, PrivateFileError) as error:
        raise OperatorError("cannot lock Hermes operator audit journal") from error


def write_audit_record(
    repo: Path,
    action: str,
    returncode: int | None,
    result: dict[str, Any],
    *,
    phase: str = "completed",
    correlation_id: str | None = None,
) -> None:
    if phase not in {"intent", "completed", "failed"}:
        raise OperatorError("Hermes operator audit phase is invalid")
    correlation_id = correlation_id or uuid.uuid4().hex
    path = audit_path(repo)
    with audit_writer_lock(path) as (parent_fd, _created_lock):
        try:
            nofollow = getattr(os, "O_NOFOLLOW", 0)
            created_journal = False
            try:
                fd = os.open(
                    path.name,
                    os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL | nofollow,
                    0o600,
                    dir_fd=parent_fd,
                )
                created_journal = True
            except FileExistsError:
                fd = os.open(
                    path.name, os.O_RDWR | os.O_APPEND | nofollow, dir_fd=parent_fd
                )
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise OSError("audit journal is not a regular file")
                os.fchmod(fd, 0o600)
                if created_journal:
                    _fsync_descriptor(parent_fd)
                with os.fdopen(os.dup(fd), "rb") as journal:
                    previous_hash, _ = read_audit_stream(journal)
                summary = (
                    result.get("plan") if isinstance(result.get("plan"), dict) else None
                )
                record = {
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "correlation_id": correlation_id,
                    "phase": phase,
                    "action": action,
                    "returncode": returncode,
                    "ok": None if phase == "intent" else returncode == 0,
                    "plan": {
                        "destructive": bool(summary and summary.get("destructive")),
                        "resource_changes": (
                            summary.get("resource_changes", {}) if summary else {}
                        ),
                    },
                    "previous_hash": previous_hash,
                }
                record["record_hash"] = audit_record_hash(record)
                os.write(
                    fd,
                    (
                        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                    ).encode(),
                )
                os.fsync(fd)
            finally:
                os.close(fd)
        except (OSError, AuditChainError, PrivateFileError) as error:
            raise OperatorError(
                "cannot durably append Hermes operator audit record"
            ) from error


def default_runner(
    command: list[str], env: dict[str, str], repo: Path
) -> tuple[int, str]:
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
    runner: Callable[
        [list[str], dict[str, str], Path], tuple[int, str] | int
    ] = default_runner,
) -> dict[str, Any]:
    if action not in {"validate", "plan", "apply"}:
        raise OperatorError(f"unsupported operator action: {action}")
    summary: dict[str, Any] | None = None
    if action == "apply":
        if not mutation_enabled():
            raise OperatorError(
                "infrastructure mutation is unavailable during the hard read-only pilot"
            )
        if not approve:
            raise OperatorError("apply requires explicit approval via --approve")
        summary = load_plan_summary(repo)
        if summary is None:
            raise OperatorError("apply requires a saved plan; run just plan first")
        if summary.get("destructive") and not allow_destructive:
            raise OperatorError("destructive apply requires --allow-destructive")
        if len(summary.get("stateful_targets", [])) > 1 and not allow_stateful_batch:
            raise OperatorError(
                "multi-service stateful apply requires --allow-stateful-batch"
            )

    env = dict(os.environ)
    if allow_destructive:
        env["INFRA_ALLOW_DESTROY"] = "1"
    if allow_stateful_batch:
        env["INFRA_ALLOW_STATEFUL_BATCH"] = "1"
    command = ["just", action]
    correlation_id = uuid.uuid4().hex
    intent: dict[str, Any] = {}
    if action == "apply":
        intent["plan"] = summary
    write_audit_record(
        repo,
        action,
        None,
        intent,
        phase="intent",
        correlation_id=correlation_id,
    )
    if action == "apply":
        snapshot_error = AuditSnapshotError
        try:
            snapshot = create_snapshot(audit_path(repo), audit_backup_dir())
            verify_snapshot(snapshot)
        except (snapshot_error, OSError, OperatorError) as error:
            write_audit_record(
                repo,
                action,
                1,
                intent,
                phase="failed",
                correlation_id=correlation_id,
            )
            raise OperatorError(
                "apply blocked because the pre-execution audit snapshot failed",
                correlation_id=correlation_id,
            ) from error
    try:
        result = runner(command, env, repo)
        if isinstance(result, tuple):
            if len(result) != 2:
                raise ValueError("runner returned an invalid result tuple")
            returncode, output = result
        else:
            returncode, output = result, ""
        if isinstance(returncode, bool) or not isinstance(returncode, int):
            raise ValueError("runner return code is invalid")
        if not isinstance(output, str):
            raise ValueError("runner output is invalid")
        safe_output = redact_output(output)
        response: dict[str, Any] = {
            "action": action,
            "correlation_id": correlation_id,
            "returncode": returncode,
            "ok": returncode == 0,
            "output": safe_output,
        }
        if action in {"plan", "apply"} and plan_metadata_path(repo).is_file():
            response["plan"] = load_plan_summary(repo)
    except Exception as error:
        write_audit_record(
            repo,
            action,
            1,
            intent,
            phase="failed",
            correlation_id=correlation_id,
        )
        raise OperatorError(
            "operator action execution or result validation failed",
            correlation_id=correlation_id,
        ) from error
    write_audit_record(
        repo,
        action,
        returncode,
        response,
        phase="completed" if returncode == 0 else "failed",
        correlation_id=correlation_id,
    )
    return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("status", "audit-verify", "validate", "plan", "apply")
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    parser.add_argument(
        "--approve", action="store_true", help="explicitly approve apply"
    )
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
        failure: dict[str, Any] = {
            "ok": False,
            "error": {"code": "operator_error", "message": str(error)},
        }
        if error.correlation_id is not None:
            failure["correlation_id"] = error.correlation_id
        encoded = json.dumps(failure, sort_keys=True)
        print(encoded, file=sys.stdout if args.json else sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
