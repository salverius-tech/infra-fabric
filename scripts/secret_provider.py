#!/usr/bin/env python3
"""Provider-neutral access to encrypted canonical site secrets."""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.parser import ParserError
from ruamel.yaml.tokens import AliasToken, AnchorToken


class SecretProviderError(ValueError):
    """Raised for secret loading, schema, or logical-path failures."""


class SecretProvider(Protocol):
    def resolve(self, logical_path: str) -> str: ...

    def describe(self, logical_path: str) -> dict[str, str]: ...

    def secret_digest(self, logical_paths: set[str] | None = None) -> str: ...

    def discover(self) -> tuple[str, ...]: ...

    def validate_required(self, logical_paths: set[str]) -> None: ...


@dataclass(frozen=True)
class SecretBundle:
    """Validated structural view of a decrypted logical secret bundle."""

    data: dict[str, Any] = field(repr=False)
    required_paths: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        paths = frozenset(_leaf_paths(self.data))
        if self.required_paths - paths:
            raise SecretProviderError("required secret path is not present in the bundle")

    def discover(self) -> tuple[str, ...]:
        return tuple(sorted(_leaf_paths(self.data)))

    def validate_required(self, logical_paths: set[str] | None = None) -> None:
        required = self.required_paths if logical_paths is None else frozenset(logical_paths)
        for path in sorted(required):
            _resolve(self.data, path)


@dataclass(frozen=True)
class SecretIdentity:
    ciphertext_hash: str
    secret_digest: str


class SopsAgeProvider:
    """Decrypt one SOPS YAML bundle in memory and resolve dotted paths.

    The subprocess receives only the source path and emits decrypted YAML on
    stdout. The provider never prints command output or secret values.
    """

    def __init__(
        self,
        path: Path,
        *,
        executable: str = "sops",
        environment: dict[str, str] | None = None,
        key_file: Path | None = None,
        required_paths: set[str] | None = None,
    ) -> None:
        self.path = path.resolve()
        self.executable = executable
        self.environment = environment or {}
        configured_key = key_file or (Path(self.environment["SOPS_AGE_KEY_FILE"]) if "SOPS_AGE_KEY_FILE" in self.environment else None)
        self.key_file = discover_age_key_file(configured_key, environment=self.environment) if configured_key else None
        self._bundle = SecretBundle(self._decrypt(), frozenset(required_paths or ()))
        self._data = self._bundle.data

    def _decrypt(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise SecretProviderError(f"secret bundle does not exist: {self.path}")
        env = os.environ.copy()
        env.update(self.environment)
        env.pop("SOPS_AGE_KEY", None)
        if self.key_file is not None:
            env["SOPS_AGE_KEY_FILE"] = str(self.key_file)
        try:
            result = subprocess.run(
                [self.executable, "--decrypt", "--input-type", "yaml", "--output-type", "yaml", str(self.path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        except OSError as error:
            raise SecretProviderError("SOPS executable is unavailable") from error
        if result.returncode != 0:
            raise SecretProviderError("SOPS could not decrypt the selected secret bundle")
        try:
            data = _strict_yaml(result.stdout)
        except SecretProviderError as error:
            raise SecretProviderError("decrypted secret bundle is invalid") from error
        return data

    def resolve(self, logical_path: str) -> str:
        return _resolve(self._data, logical_path)

    def discover(self) -> tuple[str, ...]:
        return self._bundle.discover()

    def validate_required(self, logical_paths: set[str]) -> None:
        self._bundle.validate_required(logical_paths)

    def describe(self, logical_path: str) -> dict[str, str]:
        self.resolve(logical_path)
        return {"path": logical_path, "provider": "sops-age", "classification": "logical"}

    def secret_digest(self, logical_paths: set[str] | None = None) -> str:
        paths = sorted(logical_paths or _leaf_paths(self._data))
        values = {path: self.resolve(path) for path in paths}
        payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def identity(self, logical_paths: set[str] | None = None) -> SecretIdentity:
        return SecretIdentity(
            ciphertext_hash=hashlib.sha256(self.path.read_bytes()).hexdigest(),
            secret_digest=self.secret_digest(logical_paths),
        )


_LOGICAL_PART_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_SOPS_PUBLIC_SCOPE = r"^values/sites/[^/]+/secrets\.sops\.yaml$"
_PLACEHOLDER_RECIPIENT = "age1REPLACE_WITH_SITE_RECIPIENT"


def _sops_site_scope(site: str) -> str:
    return f"^values/sites/{site}/secrets\\.sops\\.yaml$"


def canonical_sops_filename(bundle: Path) -> str:
    """Return the exact site-relative filename used by private SOPS policy."""
    resolved = bundle.expanduser().resolve()
    parts = resolved.parts
    for index in range(len(parts) - 3):
        if parts[index : index + 2] == ("values", "sites"):
            site = parts[index + 2]
            if (
                _LOGICAL_PART_RE.fullmatch(site)
                and index + 3 == len(parts) - 1
                and parts[index + 3] == "secrets.sops.yaml"
            ):
                return f"values/sites/{site}/secrets.sops.yaml"
    raise SecretProviderError("canonical SOPS bundle path is invalid")


def sops_policy_recipients(policy_path: Path, *, site: str) -> set[str]:
    """Return the public age recipient set from one exact-site SOPS policy."""
    if not _LOGICAL_PART_RE.fullmatch(site):
        raise SecretProviderError("invalid selected site for SOPS policy")
    try:
        document = _strict_yaml(policy_path.read_text(encoding="utf-8"))
    except (OSError, SecretProviderError) as error:
        raise SecretProviderError("SOPS policy is unavailable or invalid") from error
    rules = document.get("creation_rules")
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict):
        raise SecretProviderError("SOPS policy must contain one creation rule")
    rule = rules[0]
    if rule.get("path_regex") != _sops_site_scope(site):
        raise SecretProviderError("SOPS policy scope is invalid")
    age = rule.get("age")
    recipients = [age] if isinstance(age, str) else age if isinstance(age, list) else []
    if not recipients or any(not isinstance(item, str) or not item for item in recipients):
        raise SecretProviderError("SOPS recipient policy is invalid")
    recipient_set = set(recipients)
    if _PLACEHOLDER_RECIPIENT in recipient_set:
        raise SecretProviderError("SOPS recipient policy is not operational")
    return recipient_set


def inspect_sops_policy(
    policy_path: Path,
    *,
    site: str,
    expected_recipients: set[str] | None = None,
) -> dict[str, str]:
    """Inspect public SOPS policy metadata without decrypting or reading keys."""
    if not _LOGICAL_PART_RE.fullmatch(site):
        raise SecretProviderError("invalid selected site for SOPS policy")
    try:
        document = _strict_yaml(policy_path.read_text(encoding="utf-8"))
    except (OSError, SecretProviderError) as error:
        raise SecretProviderError("SOPS policy is unavailable or invalid") from error
    rules = document.get("creation_rules")
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict):
        raise SecretProviderError("SOPS policy must contain one creation rule")
    rule = rules[0]
    scope = rule.get("path_regex")
    age = rule.get("age")
    recipients = [age] if isinstance(age, str) else age if isinstance(age, list) else []
    if not recipients or any(not isinstance(item, str) or not item for item in recipients):
        raise SecretProviderError("SOPS recipient policy is invalid")
    recipient_set = set(recipients)
    if _PLACEHOLDER_RECIPIENT in recipient_set:
        if scope != _SOPS_PUBLIC_SCOPE:
            raise SecretProviderError("SOPS policy scope is invalid")
        if len(recipient_set) != 1 or expected_recipients is not None:
            raise SecretProviderError("SOPS recipient policy is not operational")
        state = "not-configured"
    else:
        if scope != _sops_site_scope(site):
            raise SecretProviderError("SOPS policy scope is invalid")
        if expected_recipients is not None and recipient_set != expected_recipients:
            raise SecretProviderError("SOPS recipient policy does not match")
        state = "verified" if expected_recipients is not None else "configured"
    return {
        "policy_scope": f"values/sites/{site}/secrets.sops.yaml",
        "recipient_policy": state,
    }


def _parts(logical_path: str) -> list[str]:
    parts = logical_path.split(".")
    if not parts or any(not _LOGICAL_PART_RE.fullmatch(part) for part in parts):
        raise SecretProviderError("invalid logical secret path")
    return parts


def validate_canonical_secret_path(logical_path: str) -> None:
    """Reject protected paths outside canonical provider, identity, and service roots."""
    parts = _parts(logical_path)
    canonical = (
        len(parts) >= 3
        and parts[0] == "secrets"
        and parts[1] in {"bootstrap", "operator"}
    ) or (
        len(parts) >= 4
        and parts[:2] == ["secrets", "providers"]
    ) or (
        len(parts) >= 4
        and parts[0] == "services"
        and parts[1] != "providers"
        and parts[2] == "secrets"
    )
    if not canonical:
        raise SecretProviderError("secret path is outside the canonical namespace")


def _resolve(data: dict[str, Any], logical_path: str) -> str:
    value: Any = data
    for part in _parts(logical_path):
        if not isinstance(value, dict) or part not in value:
            raise SecretProviderError("required secret is missing")
        value = value[part]
    if not isinstance(value, str) or not value:
        raise SecretProviderError("secret value must be a non-empty string")
    return value


def discover_age_key_file(
    explicit: Path | None = None,
    *,
    environment: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Discover an external age key file without reading or logging its contents."""
    env = environment or os.environ
    candidate = explicit or (Path(env["SOPS_AGE_KEY_FILE"]) if env.get("SOPS_AGE_KEY_FILE") else None)
    if candidate is None:
        candidate = (home or Path.home()) / ".config" / "sops" / "age" / "keys.txt"
    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise SecretProviderError("SOPS age key file is unavailable")
    if not os.access(candidate, os.R_OK):
        raise SecretProviderError("SOPS age key file is not readable")
    if candidate.stat().st_mode & 0o077:
        raise SecretProviderError("SOPS age key file permissions are too broad")
    return candidate


def check_sops_age_availability(
    path: Path,
    *,
    executable: str = "sops",
    environment: dict[str, str] | None = None,
    key_file: Path | None = None,
    expected_recipients: set[str] | None = None,
) -> dict[str, str]:
    """Check SOPS/age prerequisites without decrypting or exposing secret material."""
    bundle = path.expanduser().resolve()
    if not bundle.is_file():
        raise SecretProviderError("SOPS secret bundle is unavailable")
    executable_path = Path(executable).expanduser() if "/" in executable else None
    resolved_executable = executable_path if executable_path is not None else Path(shutil.which(executable) or "")
    if not resolved_executable.is_file() or not os.access(resolved_executable, os.X_OK):
        raise SecretProviderError("SOPS executable is unavailable")
    discovered_key = discover_age_key_file(key_file, environment=environment)
    if expected_recipients is not None:
        validate_sops_age_recipients(bundle, expected_recipients)
        recipient_policy = "verified"
    else:
        recipient_policy = "not-configured"
    return {
        "provider": "sops-age",
        "bundle_classification": "encrypted-yaml",
        "ciphertext_hash": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "key_file_classification": "external-private-key",
        "key_file_mode": oct(discovered_key.stat().st_mode & 0o777),
        "recipient_policy": recipient_policy,
    }


def validate_sops_age_recipients(path: Path, expected_recipients: set[str]) -> None:
    """Require the encrypted bundle's SOPS age recipients to match policy.

    Only public SOPS metadata is inspected; encrypted payload values are never
    resolved by this check. Errors intentionally do not identify keys or
    recipients.
    """
    if not expected_recipients or any(
        not isinstance(item, str) or not item or "REPLACE_WITH" in item
        for item in expected_recipients
    ):
        raise SecretProviderError("SOPS recipient policy is invalid")
    try:
        yaml = YAML(typ="safe")
        yaml.allow_duplicate_keys = False
        text = path.read_text(encoding="utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                raise SecretProviderError("SOPS recipient metadata is invalid")
        document = yaml.load(text)
    except SecretProviderError:
        raise
    except (OSError, DuplicateKeyError, ParserError, ValueError) as error:
        raise SecretProviderError("SOPS recipient metadata is unavailable") from error
    if not isinstance(document, dict) or not isinstance(document.get("sops"), dict):
        raise SecretProviderError("SOPS recipient metadata is unavailable")
    age_entries = document["sops"].get("age")
    if not isinstance(age_entries, list):
        raise SecretProviderError("SOPS age recipient metadata is invalid")
    actual: set[str] = set()
    for entry in age_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("recipient"), str) or not entry["recipient"]:
            raise SecretProviderError("SOPS age recipient metadata is invalid")
        actual.add(entry["recipient"])
    if actual != expected_recipients:
        raise SecretProviderError("SOPS age recipient policy does not match")


@contextmanager
def secret_material_directory(parent: Path | None = None) -> Iterator[Path]:
    """Create a private temporary directory and remove it on every exit path."""
    directory = Path(tempfile.mkdtemp(prefix="canonical-secrets-", dir=parent))
    directory.chmod(0o700)
    previous_handlers: dict[int, Any] = {}

    def cleanup() -> None:
        shutil.rmtree(directory, ignore_errors=True)

    def handle_signal(signum: int, _frame: Any) -> None:
        cleanup()
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        raise SystemExit(128 + signum)

    install_handlers = threading.current_thread() is threading.main_thread()
    try:
        if install_handlers:
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, handle_signal)
        yield directory
    finally:
        cleanup()
        if install_handlers:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def write_secret_material(directory: Path, name: str, content: str) -> Path:
    """Write controlled secret material with mode 0600; reject path traversal."""
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise SecretProviderError("invalid secret material path")
    target = directory / relative
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    target.chmod(0o600)
    return target


def _strict_yaml(text: str) -> dict[str, Any]:
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    try:
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                raise SecretProviderError("secret YAML anchors and aliases are not permitted")
        data = yaml.load(text)
    except (DuplicateKeyError, ParserError, ValueError) as error:
        raise SecretProviderError("secret YAML is invalid") from error
    if not isinstance(data, dict):
        raise SecretProviderError("secret YAML must contain a mapping")
    return data


def _leaf_paths(data: dict[str, Any], prefix: str = "") -> list[str]:
    paths: list[str] = []
    for key, value in data.items():
        if not isinstance(key, str):
            raise SecretProviderError("secret YAML keys must be strings")
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            paths.extend(_leaf_paths(value, path))
        elif isinstance(value, str):
            paths.append(path)
        else:
            raise SecretProviderError(f"secret leaf must be a non-empty string: {path}")
    return paths


__all__ = [
    "SecretBundle",
    "SecretIdentity",
    "SecretProvider",
    "SecretProviderError",
    "SopsAgeProvider",
    "canonical_sops_filename",
    "check_sops_age_availability",
    "discover_age_key_file",
    "inspect_sops_policy",
    "sops_policy_recipients",
    "validate_canonical_secret_path",
    "validate_sops_age_recipients",
    "secret_material_directory",
    "write_secret_material",
]
