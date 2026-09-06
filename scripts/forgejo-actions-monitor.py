#!/usr/bin/env python3
"""Read-only Forgejo Actions monitor for the private values repository."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from values_context import ValuesContextError, from_environment
from canonical_projections import (
    render_projection_set,
    verify_cross_projection_identity,
)
from canonical_values import load_site, model_digest
from projection_manifest import verify_manifest
from service_catalog import load_catalog

REPO = Path(__file__).resolve().parents[1]
INVENTORY = "values/ansible/inventory/local.yml"
HOST = "pve"

STATUS = {
    0: "unknown",
    1: "success",
    2: "failure",
    3: "cancelled",
    4: "skipped",
    5: "waiting",
    6: "running",
    7: "blocked",
}
TERMINAL_OK = {"success", "skipped"}
TERMINAL_BAD = {"failure", "cancelled", "blocked", "unknown"}
TERMINAL = TERMINAL_OK | TERMINAL_BAD
OUTPUT_SCHEMA_VERSION = 1
MAX_STATUS_ROWS = 50
MAX_RUNNERS = 100
MAX_SAFE_ID = (1 << 63) - 1
MAX_TIMESTAMP = 4_102_444_800  # 2100-01-01; bounds derived display text.
SAFE_EVENTS = {
    "push",
    "pull_request",
    "pull_request_target",
    "workflow_dispatch",
    "repository_dispatch",
    "schedule",
    "release",
}
SAFE_SERVICE_STATES = {
    "active",
    "inactive",
    "failed",
    "activating",
    "deactivating",
    "reloading",
    "maintenance",
}


class MonitorError(RuntimeError):
    pass


def status_name(value: int | str | None) -> str:
    try:
        return STATUS[int(value)]
    except (TypeError, ValueError, KeyError):
        return "unknown"


def safe_int(value: object, *, maximum: int = MAX_SAFE_ID) -> int | None:
    """Return a bounded non-negative integer, never attacker-controlled text."""
    if isinstance(value, bool):
        return None
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return result if 0 <= result <= maximum else None


def bounded_limit(value: object, maximum: int) -> int:
    parsed = safe_int(value)
    return min(parsed, maximum) if parsed and parsed > 0 else 1


def safe_event(value: object) -> str:
    return value if isinstance(value, str) and value in SAFE_EVENTS else "unknown"


def safe_service_state(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    return normalized if normalized in SAFE_SERVICE_STATES else "unknown"


def safe_timestamp(value: object) -> int | None:
    return safe_int(value, maximum=MAX_TIMESTAMP)


def age(timestamp: int | str | None) -> str:
    value = safe_timestamp(timestamp)
    if not value:
        return "-"
    seconds = max(0, int(datetime.now(timezone.utc).timestamp()) - value)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def duration(started: int | str | None, stopped: int | str | None) -> str:
    start = safe_timestamp(started)
    stop = safe_timestamp(stopped)
    if not start:
        return "-"
    if not stop:
        stop = int(datetime.now(timezone.utc).timestamp())
    seconds = max(0, stop - start)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minute = divmod(minutes, 60)
    return f"{hours}h{minute:02d}m"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def verify_canonical_monitor_inputs(context: object) -> Path:
    site_file = getattr(context, "canonical_site_path", None)
    if site_file is None:
        raise MonitorError("canonical site.yaml is required")
    catalog_path = REPO / "infra" / "services.json"
    try:
        model = load_site(
            site_file,
            expected_site=getattr(context, "site", None),
            catalog_path=catalog_path,
        )
        catalog = load_catalog(catalog_path)
    except Exception as error:
        raise MonitorError("canonical monitor site or catalog is invalid") from error
    expected = render_projection_set(model, catalog)
    names = tuple(expected)
    projections: dict[str, dict[str, Any]] = {}
    try:
        for name in names:
            projection = json.loads(
                getattr(context, "generated_path")(name).read_text(encoding="utf-8")
            )
            if not isinstance(projection, dict):
                raise MonitorError(
                    f"canonical monitor projection is not an object: {name}"
                )
            projections[name] = projection
        manifest = json.loads(
            getattr(context, "projection_manifest_path").read_text(encoding="utf-8")
        )
        if not isinstance(manifest, dict):
            raise MonitorError("canonical monitor manifest is not an object")
    except (OSError, json.JSONDecodeError) as error:
        raise MonitorError(
            "canonical monitor projections or manifest are unavailable"
        ) from error
    if projections != expected:
        raise MonitorError(
            "canonical monitor projections do not match the selected model"
        )
    try:
        verify_cross_projection_identity(
            site=model.site.name,
            opentofu=projections["terraform.auto.tfvars.json"],
            inventory=projections["ansible-inventory.json"],
            ansible_vars=projections["ansible-vars.json"],
        )
        verify_manifest(
            manifest,
            site=model.site.name,
            model_digest=model_digest(model),
            secret_digest=None,
            projections=projections,
        )
    except Exception as error:
        raise MonitorError(
            "canonical monitor projection identity verification failed"
        ) from error
    return getattr(context, "generated_path")("ansible-inventory.json")


def run_ansible_shell(command: str) -> str:
    if shutil.which("ansible") and Path("/workspace").exists():
        argv = ["ansible", HOST, "-i", INVENTORY, "-m", "shell", "-a", command]
    else:
        argv = [
            "bash",
            "scripts/run-infra.sh",
            "ansible",
            HOST,
            "-i",
            INVENTORY,
            "-m",
            "shell",
            "-a",
            command,
        ]
    result = subprocess.run(
        argv,
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        # Remote output is an untrusted private-data boundary. Never put it in
        # an exception that can be returned to Hermes.
        raise MonitorError("Forgejo monitor command failed")
    marker = ">>\n"
    if marker in result.stdout:
        return result.stdout.split(marker, 1)[1].strip()
    lines = [
        line
        for line in result.stdout.splitlines()
        if not line.startswith(" Container ")
    ]
    if lines and " | " in lines[0]:
        return "\n".join(lines[1:]).strip()
    return "\n".join(lines).strip()


def forgejo_sql(query: str) -> list[dict[str, Any]]:
    escaped = shell_quote(query)
    command = (
        "pct exec {{ forgejo_vmid | string }} -- runuser -u git -- "
        f"sqlite3 -readonly -json /var/lib/forgejo/data/forgejo.db {escaped}"
    )
    raw = run_ansible_shell(command)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise MonitorError("Forgejo monitor returned invalid data") from error
    if not isinstance(parsed, list) or not all(isinstance(row, dict) for row in parsed):
        raise MonitorError("Forgejo monitor returned invalid data")
    return parsed


def safe_status_row(row: dict[str, Any]) -> dict[str, Any]:
    """Project a database row into a fixed, public-safe status schema."""
    return {
        "run_id": safe_int(row.get("id")),
        "status": status_name(row.get("status")),
        "event": safe_event(row.get("event")),
        "age": age(row.get("created")),
        "duration": duration(row.get("started"), row.get("stopped")),
        "job_status": status_name(row.get("job_status")),
    }


def status_payload(rows: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    selected_limit = bounded_limit(limit, MAX_STATUS_ROWS)
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "kind": "forgejo_actions_status",
        "runs": [safe_status_row(row) for row in rows[:selected_limit]],
        "truncated": len(rows) > selected_limit,
    }


def safe_label_count(value: object) -> int:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return 0
    if not isinstance(value, list):
        return 0
    return min(len(value), 999)


def safe_runner_row(row: dict[str, Any]) -> dict[str, Any]:
    scope = "global"
    if safe_int(row.get("repo_id")):
        scope = "repo"
    elif safe_int(row.get("owner_id")):
        scope = "owner"
    return {
        "runner_id": safe_int(row.get("id")),
        "scope": scope,
        "last_seen": age(row.get("last_online")),
        "label_count": safe_label_count(row.get("agent_labels")),
    }


def runners_payload(rows: list[dict[str, Any]], service: object) -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "kind": "forgejo_actions_runners",
        "service": safe_service_state(service),
        "runners": [safe_runner_row(row) for row in rows[:MAX_RUNNERS]],
        "truncated": len(rows) > MAX_RUNNERS,
    }


def latest_runs(limit: int) -> list[dict[str, Any]]:
    selected_limit = bounded_limit(limit, MAX_STATUS_ROWS)
    return forgejo_sql(
        "select r.id, r.status, r.event, r.workflow_id, r.created, r.updated, "
        "coalesce(j.name, '-') as job_name, coalesce(j.status, 0) as job_status, "
        "coalesce(j.task_id, 0) as task_id, coalesce(j.started, 0) as started, "
        "coalesce(j.stopped, 0) as stopped "
        "from action_run r left join action_run_job j on j.run_id = r.id "
        f"order by r.id desc limit {selected_limit + 1}"
    )


def print_status(limit: int, as_json: bool) -> None:
    payload = status_payload(latest_runs(limit), limit)
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(
        f"{'RUN':>19}  {'STATUS':<9}  {'EVENT':<20}  {'AGE':>6}  {'DURATION':>9}  JOB"
    )
    for row in payload["runs"]:
        run_id = row["run_id"] if row["run_id"] is not None else "-"
        print(
            f"{run_id:>19}  {row['status']:<9}  {row['event']:<20}  "
            f"{row['age']:>6}  {row['duration']:>9}  {row['job_status']}"
        )
    if payload["truncated"]:
        print("additional runs omitted")


def run_id_or_latest(value: str) -> int:
    if value != "latest":
        run_id = safe_int(value)
        if not run_id:
            raise MonitorError("run identifier is invalid")
        return run_id
    rows = forgejo_sql("select id from action_run order by id desc limit 1")
    if not rows:
        raise MonitorError("no Forgejo Actions runs found")
    run_id = safe_int(rows[0].get("id"))
    if not run_id:
        raise MonitorError("Forgejo monitor returned invalid data")
    return run_id


def run_state(run_id: int) -> dict[str, Any]:
    rows = forgejo_sql(
        "select r.id, r.status, r.workflow_id, coalesce(j.name, '-') as job_name, "
        "coalesce(j.status, 0) as job_status, coalesce(j.started, 0) as started, "
        "coalesce(j.stopped, 0) as stopped, coalesce(j.task_id, 0) as task_id "
        "from action_run r left join action_run_job j on j.run_id = r.id "
        f"where r.id = {int(run_id)} limit 1"
    )
    if not rows:
        raise MonitorError(f"run {run_id} not found")
    return rows[0]


def watch(run: str, interval: int, timeout: int) -> int:
    run_id = run_id_or_latest(run)
    deadline = time.monotonic() + timeout if timeout else None
    last = ""
    while True:
        row = run_state(run_id)
        safe_row = safe_status_row(row)
        current = safe_row["status"]
        job = safe_row["job_status"]
        line = f"run {run_id}: {current} job {job} duration {safe_row['duration']}"
        if line != last:
            print(line, flush=True)
            last = line
        if current in TERMINAL:
            return 0 if current in TERMINAL_OK else 1
        if deadline and time.monotonic() > deadline:
            print(f"run {run_id}: monitor timeout", file=sys.stderr)
            return 124
        time.sleep(interval)


def print_runners(as_json: bool) -> None:
    rows = forgejo_sql(
        "select id, name, owner_id, repo_id, last_online, last_active, agent_labels "
        f"from action_runner order by id limit {MAX_RUNNERS + 1}"
    )
    service_output = run_ansible_shell(
        "pct exec {{ forgejo_runner_vmid | string }} -- systemctl is-active forgejo-runner || true"
    )
    service_lines = service_output.splitlines()
    service = service_lines[-1].strip() if service_lines else "unknown"
    payload = runners_payload(rows, service)
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"runner service: {payload['service']}")
    print(f"{'ID':>19}  {'SCOPE':<8}  {'LAST_SEEN':>9}  LABEL_COUNT")
    for row in payload["runners"]:
        runner_id = row["runner_id"] if row["runner_id"] is not None else "-"
        print(
            f"{runner_id:>19}  {row['scope']:<8}  "
            f"{row['last_seen']:>9}  {row['label_count']}"
        )
    if payload["truncated"]:
        print("additional runners omitted")


def print_logs(run: str, tail: int, unsafe: bool) -> None:
    run_id = run_id_or_latest(run)
    command = "pct exec {{ forgejo_vmid | string }} -- bash -lc " + shell_quote(
        "path=$(find /var/lib/forgejo/data/actions_log -type f -name '"
        + str(run_id)
        + ".log.zst' | sort | tail -n1); "
        "if [ -z \"$path\" ]; then echo 'log not found'; exit 1; fi; "
        'zstdcat "$path" | tail -n ' + str(int(tail))
    )
    text = run_ansible_shell(command)
    if unsafe:
        # Deliberately available only on this direct monitor CLI. The Hermes
        # operator adapter has a fixed status/validate/plan action allowlist
        # and cannot dispatch this command or this flag.
        print(text)
        return
    line_count = min(len(text.splitlines()), bounded_limit(tail, 10_000))
    print(f"Forgejo log content redacted ({line_count} lines)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.add_argument("--limit", type=int, default=10)
    status.add_argument("--json", action="store_true")

    runners = sub.add_parser("runners")
    runners.add_argument("--json", action="store_true")

    watch_cmd = sub.add_parser("watch")
    watch_cmd.add_argument("run", nargs="?", default="latest")
    watch_cmd.add_argument("--interval", type=int, default=5)
    watch_cmd.add_argument("--timeout", type=int, default=1800)

    logs = sub.add_parser("logs")
    logs.add_argument("run", nargs="?", default="latest")
    logs.add_argument("--tail", type=int, default=200)
    logs.add_argument(
        "--unsafe-no-redact",
        action="store_true",
        help="direct terminal use only; unavailable through the Hermes operator adapter",
    )

    args = parser.parse_args(argv)
    global INVENTORY
    try:
        context = from_environment(REPO)
        if context.site is None:
            raise MonitorError("VALUES_SITE is required for Forgejo Actions monitoring")
        if context.canonical_site_path is None:
            raise MonitorError("canonical site.yaml is required")
        inventory = verify_canonical_monitor_inputs(context)
        if not inventory.is_file():
            raise MonitorError("canonical generated inventory is missing")
        INVENTORY = str(inventory)
        if args.command == "status":
            print_status(args.limit, args.json)
        elif args.command == "runners":
            print_runners(args.json)
        elif args.command == "watch":
            return watch(args.run, args.interval, args.timeout)
        elif args.command == "logs":
            print_logs(args.run, args.tail, args.unsafe_no_redact)
    except ValuesContextError:
        print("Forgejo monitor context is invalid", file=sys.stderr)
        return 2
    except MonitorError as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
