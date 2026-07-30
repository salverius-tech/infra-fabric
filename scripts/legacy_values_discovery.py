"""Read-only discovery of legacy private-values inputs.

This module deliberately reports migration work instead of rewriting legacy files.
It never generates, hashes, moves, deletes, or serializes secret values.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class DiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class FieldObservation:
    source: str
    key: str
    classification: str
    proposed_path: str | None
    value_type: str
    value: Any = None


@dataclass
class DiscoveryReport:
    values_dir: str
    observations: list[FieldObservation] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    ancillary_artifacts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def mapping_ready(self) -> bool:
        return any(item.classification == "mapped" for item in self.observations) and not self.conflicts and not any(
            item.classification in {"unknown", "unsupported"} for item in self.observations
        )

    @property
    def candidate_ready(self) -> bool:
        """Strict candidate readiness remains false until runtime admission exists."""
        return False


def _load_migration_module() -> Any:
    path = Path(__file__).with_name("migrate-values.py")
    spec = importlib.util.spec_from_file_location("legacy_migration_helpers", path)
    if spec is None or spec.loader is None:
        raise DiscoveryError(f"cannot load legacy parser: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _classification(key: str, migration: Any) -> tuple[str, str | None]:
    if key in migration.SECRET_KEYS or key.startswith("TF_VAR_") and key.removeprefix("TF_VAR_") in {
        "container_root_password",
        "lxc_root_password",
    }:
        return "secret", None
    paths = {
        "PROXMOX_VE_API_URL": "platform.proxmox.endpoint",
        "PROXMOX_VE_ENDPOINT": "platform.proxmox.endpoint",
        "PROXMOX_NODE_NAME": "platform.proxmox.node",
        "TECHNITIUM_API_URL": "services.technitium.endpoints.public_url",
        "technitium_api_url": "services.technitium.endpoints.public_url",
        "SERVER_NAME": "services.technitium.endpoints.public_names",
        "server_name": "services.technitium.endpoints.public_names",
        "infisical_server_name": "services.infisical.endpoints.public_names",
        "INFISICAL_SERVER_NAME": "services.infisical.endpoints.public_names",
        "infisical_domain": "services.infisical.endpoints.public_names",
        "FORGEJO_DOMAIN": "services.forgejo.endpoints.public_names",
        "forgejo_domain": "services.forgejo.endpoints.public_names",
        "FORGEJO_SERVER_NAME": "services.forgejo.endpoints.public_names",
        "forgejo_server_name": "services.forgejo.endpoints.public_names",
        "FORGEJO_VERSION": "services.forgejo.release.version",
        "forgejo_version": "services.forgejo.release.version",
        "FORGEJO_SSH_PORT": "services.forgejo.endpoints.ports.ssh",
        "forgejo_ssh_port": "services.forgejo.endpoints.ports.ssh",
        "HERMES_CONTROL_SOURCE_URL": "services.hermes.configuration.control.source_url",
        "HERMES_CONTROL_SOURCE_REF": "services.hermes.configuration.control.source_ref",
    }
    if key in paths:
        return "mapped", paths[key]
    if key in migration.GENERATED_SECRET_KEYS:
        return "secret", None
    return "unknown", None


def _public_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
        return value
    return None


def _normalize_public_name(value: Any) -> Any:
    if isinstance(value, str):
        return [value.lower().rstrip(".")]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return [item.lower().rstrip(".") for item in value]
    return value


def _normalize_port(value: Any) -> Any:
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return value


def _observe(source: str, key: str, value: Any, report: DiscoveryReport, migration: Any) -> None:
    classification, proposed_path = _classification(key, migration)
    if classification == "secret":
        report.observations.append(FieldObservation(source, key, classification, None, type(value).__name__, "<redacted>"))
        return
    public = _public_value(value)
    if proposed_path in {
        "services.technitium.endpoints.public_names",
        "services.infisical.endpoints.public_names",
        "services.forgejo.endpoints.public_names",
    }:
        public = _normalize_public_name(public)
    value_type = type(value).__name__
    if proposed_path == "services.forgejo.endpoints.ports.ssh":
        public = _normalize_port(public)
    if classification == "unknown":
        public = None
    observation = FieldObservation(source, key, classification, proposed_path, value_type, public)
    for previous in report.observations:
        if previous.proposed_path == proposed_path and proposed_path is not None and previous.value != public:
            report.conflicts.append(
                {
                    "canonical_path": proposed_path,
                    "sources": [previous.source, source],
                    "keys": [previous.key, key],
                    "disposition": "manual review required",
                }
            )
    report.observations.append(observation)


def _read_env(path: Path, report: DiscoveryReport, migration: Any) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    entries = migration.parse_env_lines(lines, path)
    for key, entry in entries.items():
        _observe(path.relative_to(path.parents[1]).as_posix(), key, entry.value, report, migration)


def _read_tfvars(path: Path, report: DiscoveryReport, migration: Any) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for key, (_line, value) in migration.parse_tfvars(lines, path).items():
        _observe(path.relative_to(path.parents[1]).as_posix(), key, value, report, migration)
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
    known = set(migration.parse_tfvars(lines, path))
    for line in lines:
        match = pattern.match(line)
        if match and match.group(1) not in known:
            key = match.group(1)
            classification, _ = _classification(key, migration)
            value = migration.tfvars_scalar_value(lines, key) if classification == "mapped" else None
            _observe(path.relative_to(path.parents[1]).as_posix(), key, value, report, migration)


def _read_json_keys(path: Path, report: DiscoveryReport, migration: Any) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DiscoveryError(f"invalid JSON legacy input: {path}") from error
    if not isinstance(value, dict):
        raise DiscoveryError(f"legacy JSON input must be an object: {path}")
    source = path.relative_to(path.parents[1]).as_posix()
    for key, item in value.items():
        _observe(source, str(key), item, report, migration)


def _artifact_relative(values: Path, path: Path) -> str:
    """Return a contained, non-symlinked artifact path for metadata reporting."""
    try:
        relative = path.relative_to(values)
    except ValueError as error:
        raise DiscoveryError("legacy artifact path escapes the values directory") from error
    current = values
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise DiscoveryError("legacy artifact symlinks are not supported")
    return relative.as_posix()


def _record_artifact(report: DiscoveryReport, values: Path, path: Path, artifact_class: str) -> None:
    relative = _artifact_relative(values, path)
    if not path.is_file():
        raise DiscoveryError("legacy artifact must be a regular file")
    report.ancillary_artifacts.append(
        {
            "path": relative,
            "class": artifact_class,
            "present": True,
            "size_bytes": path.stat().st_size,
        }
    )


def _record_artifact_tree(report: DiscoveryReport, values: Path, root: Path, artifact_class: str) -> None:
    _artifact_relative(values, root)
    if root.is_symlink():
        raise DiscoveryError("legacy artifact symlinks are not supported")
    if not root.is_dir():
        raise DiscoveryError("legacy artifact tree must be a directory")
    regular_files: list[Path] = []
    for path in sorted(root.rglob("*")):
        _artifact_relative(values, path)
        if path.is_symlink():
            raise DiscoveryError("legacy artifact symlinks are not supported")
        if path.is_file():
            regular_files.append(path)
        elif not path.is_dir():
            raise DiscoveryError("legacy artifact tree contains a non-regular entry")
    report.ancillary_artifacts.append(
        {
            "path": _artifact_relative(values, root),
            "class": artifact_class,
            "present": True,
            "file_count": len(regular_files),
            "size_bytes": sum(path.stat().st_size for path in regular_files),
        }
    )


def _read_ansible_forgejo_slice(path: Path, report: DiscoveryReport, migration: Any) -> None:
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - environment setup failure
        raise DiscoveryError("PyYAML is required for bounded Ansible importer discovery") from error
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DiscoveryError(f"cannot parse Ansible inventory: {path}") from error
    try:
        variables = document["all"]["vars"]
        domain = variables["forgejo_domain"]
    except (KeyError, TypeError) as error:
        raise DiscoveryError("bounded Ansible importer requires all.vars.forgejo_domain") from error
    if not isinstance(domain, str) or not domain.strip():
        raise DiscoveryError("bounded Ansible forgejo_domain must be a non-empty string")
    source = path.as_posix()
    _observe(source, "forgejo_domain", domain, report, migration)
    if "forgejo_version" in variables:
        version = variables["forgejo_version"]
        if not isinstance(version, str) or not version.strip():
            raise DiscoveryError("bounded Ansible forgejo_version must be a non-empty string")
        _observe(source, "forgejo_version", version, report, migration)
    report.observations.append(FieldObservation(source, "<inventory:remaining>", "unsupported", None, "yaml"))


def _discover_ancillary_artifacts(values: Path, report: DiscoveryReport) -> None:
    known_hosts = values / "ansible" / "known_hosts"
    if known_hosts.exists() or known_hosts.is_symlink():
        _record_artifact(report, values, known_hosts, "known-hosts")
    for state in sorted(values.glob("terraform.tfstate*")):
        if state.exists() or state.is_symlink():
            _record_artifact(report, values, state, "terraform-state")
    backups = values / "service-backups"
    if backups.exists() or backups.is_symlink():
        _record_artifact_tree(report, values, backups, "service-backups")
    for plan in sorted(values.glob("tfplan*")):
        if plan.exists() or plan.is_symlink():
            _record_artifact(report, values, plan, "terraform-plan")
    artifacts = values / "artifacts"
    if artifacts.exists() or artifacts.is_symlink():
        _record_artifact_tree(report, values, artifacts, "general-artifacts")
    backups = values / "backups"
    if backups.exists() or backups.is_symlink():
        _record_artifact_tree(report, values, backups, "recovery-backups")


def discover_legacy(
    values_dir: Path,
    repo: Path | None = None,
    ansible_inventory: Path | None = None,
) -> DiscoveryReport:
    """Read legacy inputs and return a redacted migration review report."""
    values = values_dir.resolve()
    if not values.is_dir():
        raise DiscoveryError(f"legacy values directory does not exist: {values}")
    migration = _load_migration_module()
    report = DiscoveryReport(values_dir=str(values))
    candidates = (
        (values / ".env", _read_env),
        (values / "terraform.tfvars", _read_tfvars),
        (values / "settings.local.json", _read_json_keys),
        (values / "dns-records.local.json", _read_json_keys),
    )
    for path, reader in candidates:
        if not path.is_file():
            continue
        report.files.append(path.relative_to(values).as_posix())
        reader(path, report, migration)
    inventory = values / "ansible" / "inventory" / "local.yml"
    if ansible_inventory is not None:
        inventory = ansible_inventory.expanduser().resolve()
        if repo is not None:
            expected = (repo.resolve() / "scaffold" / "ansible" / "inventory" / "local.yml").resolve()
            if inventory != expected:
                raise DiscoveryError("bounded Ansible importer accepts only the public scaffold inventory")
        if not inventory.is_file():
            raise DiscoveryError(f"Ansible inventory does not exist: {inventory}")
        report.files.append(inventory.as_posix())
        _read_ansible_forgejo_slice(inventory, report, migration)
    elif inventory.is_file():
        report.files.append(inventory.relative_to(values).as_posix())
        report.observations.append(
            FieldObservation(inventory.relative_to(values).as_posix(), "<inventory>", "unsupported", None, "yaml")
        )
    _discover_ancillary_artifacts(values, report)
    return report


def render_migration_report(report: DiscoveryReport) -> dict[str, Any]:
    """Return JSON-safe report data without secret values or arbitrary unknown values."""
    return {
        "values_dir": report.values_dir,
        "files": sorted(report.files),
        "mapping_ready": report.mapping_ready,
        "candidate_ready": report.candidate_ready,
        "observations": [
            {
                "source": item.source,
                "key": item.key,
                "classification": item.classification,
                "proposed_path": item.proposed_path,
                "value_type": item.value_type,
                "value": item.value,
            }
            for item in report.observations
        ],
        "conflicts": report.conflicts,
        "ancillary_artifacts": sorted(report.ancillary_artifacts, key=lambda item: item["path"]),
    }


def _set_dotted_path(document: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if any(not part or "<" in part or ">" in part for part in parts):
        raise DiscoveryError(f"candidate path is not concrete: {path}")
    current: dict[str, Any] = document
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise DiscoveryError(f"candidate path collides with a scalar: {path}")
        current = child
    current[parts[-1]] = copy.deepcopy(value)


def build_candidate_site(
    report: DiscoveryReport,
    *,
    base_document: dict[str, Any],
    site_name: str | None = None,
    runtime_importer_ready: bool = False,
) -> dict[str, Any]:
    """Overlay safe mapped observations onto an approved canonical base document."""
    if not report.mapping_ready:
        raise DiscoveryError("canonical candidate is not safe: review conflicts and unmapped legacy fields")
    if not runtime_importer_ready:
        raise DiscoveryError("canonical candidate is blocked: runtime importer admission is incomplete")
    if not isinstance(base_document, dict) or base_document.get("schema_version") != 1:
        raise DiscoveryError("candidate base document must be a canonical schema_version 1 mapping")
    candidate = copy.deepcopy(base_document)
    if site_name is not None:
        site = candidate.setdefault("site", {})
        if not isinstance(site, dict):
            raise DiscoveryError("candidate base site section must be a mapping")
        site["name"] = site_name
    for observation in report.observations:
        if observation.classification == "secret":
            continue
        if observation.classification != "mapped" or observation.proposed_path is None:
            raise DiscoveryError(f"candidate observation is not safely mapped: {observation.key}")
        _set_dotted_path(candidate, observation.proposed_path, observation.value)
    return candidate
