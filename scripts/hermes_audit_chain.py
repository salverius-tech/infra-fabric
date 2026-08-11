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
