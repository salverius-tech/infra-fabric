"""Hermes plugin for the reviewed homelab-infra operator workflow."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

_PLUGIN_ID = "homelab-infra-operator"
_ACTIONS = ("status", "validate", "plan")
_SCHEMA = {
    "name": "homelab_infra_operator",
    "description": (
        "Inspect or validate the homelab-infra repository, or create a reviewed "
        "OpenTofu plan. Actions never apply infrastructure. To apply a reviewed "
        "plan, the operator must explicitly invoke /infra-apply."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_ACTIONS),
                "description": "Read-only operator action to perform.",
            }
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def _repo() -> Path:
    value = os.environ.get("HERMES_OPERATOR_REPO_PATH", "").strip()
    if not value:
        raise RuntimeError("HERMES_OPERATOR_REPO_PATH is not configured")
    repo = Path(value).expanduser().resolve()
    script = repo / "scripts" / "hermes-operator.py"
    if not script.is_file():
        raise RuntimeError("homelab-infra operator bridge is missing")
    return repo


def _run(action: str, extra: tuple[str, ...] = ()) -> str:
    if action not in _ACTIONS and action != "apply":
        return json.dumps({"ok": False, "error": "unsupported operator action"})
    repo = _repo()
    command = [
        sys.executable,
        str(repo / "scripts" / "hermes-operator.py"),
        action,
        "--repo",
        str(repo),
        "--json",
        *extra,
    ]
    result = subprocess.run(
        command,
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = result.stdout.strip()
    if output:
        try:
            payload: Any = json.loads(output)
        except json.JSONDecodeError:
            payload = {"ok": False, "error": "operator bridge returned invalid JSON"}
    else:
        payload = {"ok": result.returncode == 0}
    if not isinstance(payload, dict):
        payload = {"ok": False, "error": "operator bridge returned invalid data"}
    payload.setdefault("returncode", result.returncode)
    return json.dumps(payload, sort_keys=True)


def _handle_operator(args: dict[str, Any], **_: Any) -> str:
    action = str(args.get("action", "")).strip().lower()
    try:
        return _run(action)
    except (OSError, RuntimeError) as error:
        return json.dumps({"ok": False, "error": str(error)})


def _handle_apply(raw_args: str) -> str:
    """Apply only when the operator explicitly invokes this slash command."""
    try:
        flags = tuple(shlex.split(raw_args or ""))
    except ValueError:
        return json.dumps({"ok": False, "error": "invalid apply arguments"})
    allowed = {"--allow-destructive", "--allow-stateful-batch"}
    if any(flag not in allowed for flag in flags):
        return json.dumps({"ok": False, "error": "unsupported apply argument"})
    try:
        return _run("apply", ("--approve", *flags))
    except (OSError, RuntimeError) as error:
        return json.dumps({"ok": False, "error": str(error)})


def register(ctx) -> None:
    ctx.register_tool(
        name="homelab_infra_operator",
        toolset="homelab_infra",
        schema=_SCHEMA,
        handler=_handle_operator,
        description="Reviewed read-only homelab-infra operator actions.",
        emoji="🏠",
    )
    ctx.register_command(
        name="infra-apply",
        help="Apply the current reviewed homelab-infra plan",
        handler=_handle_apply,
        description=(
            "Explicitly apply the saved homelab-infra plan. The operator must "
            "invoke this command; destructive changes require an extra flag."
        ),
        args_hint="[--allow-destructive] [--allow-stateful-batch]",
    )
