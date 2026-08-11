"""Importable validation for the Hermes operator's local audit journal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    from private_files import PrivateFileError, open_regular_file
except ModuleNotFoundError:  # pragma: no cover - direct import in test loaders
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from private_files import PrivateFileError, open_regular_file


class AuditChainError(RuntimeError):
    """Raised when a journal is missing, malformed, or fails integrity checks."""


SUPPORTED_AUDIT_ACTIONS = frozenset({"validate", "plan", "apply"})
AUDIT_PHASES = frozenset({"intent", "completed", "failed"})
LIFECYCLE_FIELDS = frozenset({"correlation_id", "phase", "action", "returncode", "ok"})


def audit_record_hash(record: dict[str, object]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "record_hash"}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _validated_records(handle) -> tuple[str, list[dict[str, object]]]:
    previous_hash = "0" * 64
    records: list[dict[str, object]] = []
    try:
        handle.seek(0)
        lines = handle.read().decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise AuditChainError("cannot read Hermes operator audit journal") from error
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise AuditChainError(
                "Hermes operator audit journal is malformed"
            ) from error
        if not isinstance(record, dict) or record.get("previous_hash") != previous_hash:
            raise AuditChainError(
                "Hermes operator audit journal failed chain verification"
            )
        if record.get("record_hash") != audit_record_hash(record):
            raise AuditChainError(
                "Hermes operator audit journal failed integrity verification"
            )
        previous_hash = str(record["record_hash"])
        records.append(record)
    return previous_hash, records


def validate_audit_lifecycles(records: list[dict[str, object]]) -> list[str]:
    """Validate completed operation lifecycles after chain integrity is established.

    This is deliberately separate from ``read_audit_stream``: writers must be able
    to integrity-check a journal containing an in-flight intent before appending its
    terminal record.  Explicit audit verification calls this stricter semantic gate.
    """
    lifecycles: dict[str, dict[str, object]] = {}
    for record in records:
        if not LIFECYCLE_FIELDS.issubset(record):
            raise AuditChainError(
                "Hermes operator audit lifecycle record shape is invalid"
            )

        correlation_id = record["correlation_id"]
        phase = record["phase"]
        action = record["action"]
        returncode = record["returncode"]
        ok = record["ok"]
        if (
            not isinstance(correlation_id, str)
            or len(correlation_id) != 32
            or any(character not in "0123456789abcdef" for character in correlation_id)
            or not isinstance(phase, str)
            or phase not in AUDIT_PHASES
        ):
            raise AuditChainError("Hermes operator audit lifecycle metadata is invalid")
        if not isinstance(action, str) or action not in SUPPORTED_AUDIT_ACTIONS:
            raise AuditChainError(
                "Hermes operator audit action is empty or unsupported"
            )

        if phase == "intent":
            if returncode is not None or ok is not None:
                raise AuditChainError(
                    "Hermes operator audit intent result shape is invalid"
                )
            if correlation_id in lifecycles:
                raise AuditChainError("Hermes operator audit correlation is reused")
            lifecycles[correlation_id] = {"action": action, "terminal": None}
            continue

        if isinstance(returncode, bool) or not isinstance(returncode, int):
            raise AuditChainError(
                f"Hermes operator audit {phase} result shape is invalid"
            )
        if phase == "completed" and (returncode != 0 or ok is not True):
            raise AuditChainError(
                "Hermes operator audit completed result shape is invalid"
            )
        if phase == "failed" and (returncode == 0 or ok is not False):
            raise AuditChainError(
                "Hermes operator audit failed result shape is invalid"
            )

        lifecycle = lifecycles.get(correlation_id)
        if lifecycle is None:
            raise AuditChainError("Hermes operator audit terminal record has no intent")
        if lifecycle["action"] != action:
            raise AuditChainError("Hermes operator audit lifecycle action changed")
        if lifecycle["terminal"] is not None:
            raise AuditChainError(
                "Hermes operator audit lifecycle has duplicate terminal records"
            )
        lifecycle["terminal"] = phase

    return sorted(
        correlation_id
        for correlation_id, lifecycle in lifecycles.items()
        if lifecycle["terminal"] is None
    )


def read_audit_stream(handle) -> tuple[str, int]:
    previous_hash, records = _validated_records(handle)
    return previous_hash, len(records)


def read_audit_records(path: Path) -> tuple[str, list[dict[str, object]]]:
    try:
        with open_regular_file(path, "Hermes operator audit journal") as handle:
            return _validated_records(handle)
    except PrivateFileError as error:
        if isinstance(error.__cause__, FileNotFoundError):
            raise AuditChainError(
                "Hermes operator audit journal is unavailable"
            ) from error
        raise AuditChainError("cannot read Hermes operator audit journal") from error
    except OSError as error:
        raise AuditChainError("cannot read Hermes operator audit journal") from error


def read_audit_chain(path: Path, *, allow_missing: bool = False) -> tuple[str, int]:
    try:
        with open_regular_file(path, "Hermes operator audit journal") as handle:
            return read_audit_stream(handle)
    except PrivateFileError as error:
        if isinstance(error.__cause__, FileNotFoundError):
            if allow_missing:
                return "0" * 64, 0
            raise AuditChainError(
                "Hermes operator audit journal is unavailable"
            ) from error
        raise AuditChainError("cannot read Hermes operator audit journal") from error
    except OSError as error:
        raise AuditChainError("cannot read Hermes operator audit journal") from error
