"""Executable canonical-to-consumer mapping contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class MappingContractError(ValueError):
    """Raised when a mapping path or consumer contract is invalid."""


@dataclass(frozen=True)
class MappingEntry:
    canonical_path: str
    consumers: tuple[str, ...]
    classification: str
    required: bool = False


SERVICE_MAPPING_MATRIX: tuple[MappingEntry, ...] = (
    MappingEntry("services.forgejo.resource", ("opentofu", "ansible"), "derived", required=True),
    MappingEntry("services.forgejo.release.version", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.forgejo.configuration.database", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.forgejo.configuration.enable_caddy", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.forgejo_runner.configuration.url", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.forgejo_runner.configuration.labels", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.infisical.configuration.data_dir", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.tailscale_client.configuration.restore_backup", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.tailscale_client.configuration.up_args", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.searxng_onramp.configuration.container_port", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.technitium.configuration.api_url", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.hermes.configuration.runtime_user", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.hermes.configuration.control.api_port", ("opentofu", "ansible"), "canonical"),
    MappingEntry("services.hermes.configuration.tuning.max_spawn_depth", ("opentofu", "ansible"), "canonical"),
    MappingEntry("platform.proxmox.endpoint", ("opentofu", "ansible"), "canonical"),
    MappingEntry("platform.proxmox.node", ("opentofu", "ansible"), "canonical"),
    MappingEntry("platform.storage.rootfs_datastore", ("opentofu",), "canonical"),
)

_ALLOWED_CLASSIFICATIONS = frozenset(("canonical", "derived", "compatibility", "secret"))
_ALLOWED_CONSUMERS = frozenset(("opentofu", "ansible", "inventory", "dns", "dotenv"))


def _path_value(value: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(value, Mapping):
            if part not in value:
                raise MappingContractError(f"canonical mapping path does not exist: {path}")
            value = value[part]
        elif not hasattr(value, part):
            raise MappingContractError(f"canonical mapping path does not exist: {path}")
        else:
            value = getattr(value, part)
    return value


def validate_mapping_matrix(model: Any, entries: tuple[MappingEntry, ...] = SERVICE_MAPPING_MATRIX) -> None:
    """Validate mapping metadata and ensure every path exists on ``model``."""
    seen: set[str] = set()
    for entry in entries:
        if entry.canonical_path in seen:
            raise MappingContractError(f"duplicate canonical mapping path: {entry.canonical_path}")
        seen.add(entry.canonical_path)
        if not entry.consumers or any(consumer not in _ALLOWED_CONSUMERS for consumer in entry.consumers):
            raise MappingContractError(f"unsupported mapping consumer for {entry.canonical_path}")
        if entry.classification not in _ALLOWED_CLASSIFICATIONS:
            raise MappingContractError(f"unsupported mapping classification for {entry.canonical_path}")
        try:
            value = _path_value(model, entry.canonical_path)
        except MappingContractError:
            if entry.required:
                raise
        else:
            if entry.required and (value is None or value == "" or value == []):
                raise MappingContractError(f"required canonical mapping path is empty: {entry.canonical_path}")
