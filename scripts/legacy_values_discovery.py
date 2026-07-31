"""Read-only discovery of legacy private-values inputs.

This module deliberately reports migration work instead of rewriting legacy files.
It never generates, hashes, moves, deletes, or serializes secret values.
"""
from __future__ import annotations

import copy
import importlib.util
import ipaddress
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
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
    dynamic_reference: str | None = None
    dynamic_reference_available: bool | None = None


@dataclass
class DiscoveryReport:
    values_dir: str
    observations: list[FieldObservation] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    ancillary_artifacts: list[dict[str, Any]] = field(default_factory=list)
    site_metadata: dict[str, Any] = field(default_factory=dict)

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
        "FORGEJO_ENABLE_CADDY": "services.forgejo.configuration.enable_caddy",
        "forgejo_enable_caddy": "services.forgejo.configuration.enable_caddy",
        "FORGEJO_CONFIGURE_SYSTEM_SSH": "services.forgejo.configuration.configure_system_ssh",
        "forgejo_configure_system_ssh": "services.forgejo.configuration.configure_system_ssh",
        "FORGEJO_WRITE_INITIAL_CONFIG": "services.forgejo.configuration.write_initial_config",
        "forgejo_write_initial_config": "services.forgejo.configuration.write_initial_config",
        "FORGEJO_BOOTSTRAP_ENABLED": "services.forgejo.configuration.bootstrap_enabled",
        "forgejo_bootstrap_enabled": "services.forgejo.configuration.bootstrap_enabled",
        "forgejo_bootstrap_admin_username": "services.forgejo.configuration.bootstrap_admin_username",
        "forgejo_bootstrap_admin_email": "services.forgejo.configuration.bootstrap_admin_email",
        "forgejo_bootstrap_owner_email": "services.forgejo.configuration.bootstrap_owner_email",
        "forgejo_database": "services.forgejo.configuration.database",
        "technitium_vmid": "resources.guests.technitium.identity.vmid",
        "forgejo_vmid": "resources.guests.forgejo.identity.vmid",
        "tailscale_client_vmid": "resources.guests.tailscale_client.identity.vmid",
        "onramp_host_password_authentication": "resources.shared_hosts.onramp_host.security.password_authentication",
        "onramp_host_permit_root_login": "resources.shared_hosts.onramp_host.security.permit_root_login",
        "onramp_host_deploy_user": "resources.shared_hosts.onramp_host.security.deploy_user",
        "onramp_host_deploy_dir": "resources.shared_hosts.onramp_host.security.deploy_dir",
        "onramp_host_allow_passwordless_sudo": "resources.shared_hosts.onramp_host.security.allow_passwordless_sudo",
        "onramp_host_allowed_ssh_cidrs": "resources.shared_hosts.onramp_host.security.allowed_ssh_cidrs",
        "onramp_host_cloud_init_user": "resources.shared_hosts.onramp_host.runtime.cloud_init_user",
        "onramp_host_ssh_public_keys": "resources.shared_hosts.onramp_host.security.ssh_public_keys",
        "tailscale_client_enabled": "services.tailscale_client.enabled",
        "hermes_ssh_public_keys": "resources.guests.hermes.security.ssh_public_keys",
        "searxng_server_name": "services.searxng_onramp.endpoints.public_names.0",
        "searxng_public_url": "services.searxng_onramp.endpoints.public_url",
        "searxng_container_image": "services.searxng_onramp.release",
        "FORGEJO_ACTIONS_ENABLED": "services.forgejo.configuration.actions_enabled",
        "forgejo_actions_enabled": "services.forgejo.configuration.actions_enabled",
        "FORGEJO_ACTIONS_DEFAULT_URL": "services.forgejo.configuration.actions_default_url",
        "caddy_email": "platform.ingress.acme.email",
        "caddy_server_name": "services.technitium.configuration.caddy.server_names",
        "caddy_server_names": "services.technitium.configuration.caddy.server_names",
        "caddy_upstream": "services.technitium.configuration.caddy.upstream",
        "caddy_extra_vhosts": "services.technitium.configuration.caddy.extra_vhosts",
        "forgejo_actions_default_url": "services.forgejo.configuration.actions_default_url",
        "FORGEJO_SSH_PORT": "services.forgejo.endpoints.ports.ssh",
        "forgejo_ssh_port": "services.forgejo.endpoints.ports.ssh",
        "FORGEJO_ROOT_URL": "services.forgejo.endpoints.public_url",
        "forgejo_root_url": "services.forgejo.endpoints.public_url",
        "tailscale_client_enable_ip_forwarding": "services.tailscale_client.configuration.enable_ip_forwarding",
        "tailscale_client_restore_backup": "services.tailscale_client.configuration.restore_backup",
        "tailscale_client_backup_archive": "services.tailscale_client.configuration.backup_archive",
        "tailscale_client_up_args": "services.tailscale_client.configuration.up_args",
        "searxng_container_port": "services.searxng_onramp.configuration.container_port",
        "searxng_bind_address": "services.searxng_onramp.configuration.bind_address",
        "searxng_instance_name": "services.searxng_onramp.configuration.instance_name",
        "searxng_enable_public_url": "services.searxng_onramp.configuration.enable_public_url",
        "forgejo_runner_version": "services.forgejo_runner.release.version",
        "forgejo_runner_url": "services.forgejo_runner.configuration.url",
        "forgejo_runner_name": "services.forgejo_runner.configuration.name",
        "forgejo_runner_scope": "services.forgejo_runner.configuration.scope",
        "forgejo_runner_label": "services.forgejo_runner.configuration.label",
        "forgejo_runner_labels": "services.forgejo_runner.configuration.labels",
        "forgejo_runner_hosts": "services.forgejo_runner.configuration.hosts",
        "infisical_data_dir": "services.infisical.configuration.data_dir",
        "infisical_postgres_user": "services.infisical.configuration.postgres_user",
        "infisical_postgres_db": "services.infisical.configuration.postgres_db",
        "infisical_domain": "services.infisical.endpoints.public_names",
        "infisical_version": "services.infisical.release.version",
        "infisical_vmid": "resources.guests.infisical.identity.vmid",
        "forgejo_runner_vmid": "resources.guests.forgejo_runner.identity.vmid",
        "forgejo_runner_dns_servers": "resources.guests.forgejo_runner.network.dns_servers",
        "hermes_domain": "services.hermes.endpoints.public_names",
        "hermes_runtime_user": "services.hermes.configuration.runtime_user",
        "hermes_repo_path": "services.hermes.configuration.repository_path",
        "hermes_vmid": "resources.guests.hermes.identity.vmid",
        "HERMES_CONTROL_SOURCE_URL": "services.hermes.configuration.control.source_url",
        "HERMES_CONTROL_SOURCE_REF": "services.hermes.configuration.control.source_ref",
        "hermes_control_enabled": "services.hermes.configuration.control.enabled",
        "hermes_control_domain": "services.hermes.configuration.control.domain",
        "hermes_control_api_host": "services.hermes.configuration.control.api_host",
        "hermes_control_api_port": "services.hermes.configuration.control.api_port",
        "hermes_control_require_task_approval": "services.hermes.configuration.control.require_task_approval",
        "hermes_control_plugin_socket": "services.hermes.configuration.control.plugin_socket",
        "hermes_discovery_version": "services.hermes.release.version",
        "hermes_discovery_tag": "services.hermes.release.tag",
        "hermes_discovery_commit": "services.hermes.release.commit",
        "hermes_discovery_wheel_sha256": "services.hermes.release.checksum",
        "hermes_node_version": "services.hermes.configuration.node.version",
        "hermes_node_sha256_amd64": "services.hermes.configuration.node.checksums.amd64",
        "hermes_node_sha256_arm64": "services.hermes.configuration.node.checksums.arm64",
        "hermes_dashboard_enabled": "services.hermes.configuration.dashboard.enabled",
        "hermes_dashboard_port": "services.hermes.endpoints.ports.dashboard",
        "hermes_dashboard_host": "services.hermes.configuration.dashboard.host",
        "hermes_dashboard_basic_auth_username": "services.hermes.configuration.dashboard.auth_username",
        "hermes_runtime_passwordless_sudo": "resources.guests.hermes.security.allow_passwordless_sudo",
        "hermes_allow_legacy_runtime": "services.hermes.configuration.allow_legacy_runtime",
        "hermes_compression_threshold": "services.hermes.configuration.tuning.compression_threshold",
        "hermes_max_concurrent_children": "services.hermes.configuration.tuning.max_concurrent_children",
        "hermes_max_spawn_depth": "services.hermes.configuration.tuning.max_spawn_depth",
        "hermes_web_searxng_url": "services.hermes.configuration.web.searxng_url",
        "technitium_admin_user": "services.technitium.configuration.admin_user",
        "technitium_discovery_version": "services.technitium.release.version",
        "technitium_portable_sha256": "services.technitium.release.checksum",
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
    if isinstance(value, list) and all(
        isinstance(item, dict)
        and set(item) == {"name", "address"}
        and all(isinstance(item[field], str) for field in ("name", "address"))
        for item in value
    ):
        return value
    if isinstance(value, list) and all(
        isinstance(item, dict)
        and set(item) == {"server_names", "upstream"}
        and isinstance(item["server_names"], list)
        and isinstance(item["upstream"], dict)
        and set(item["upstream"]) == {"host", "port"}
        for item in value
    ):
        return value
    if isinstance(value, dict) and set(value) <= {"type", "managed", "host", "port", "name", "user", "ssl_mode"}:
        return value
    if isinstance(value, dict) and set(value) == {"host", "port"}:
        return value
    return None


def _normalize_caddy_upstream(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise DiscoveryError("bounded Ansible caddy_upstream must be host:port")
    match = re.fullmatch(r"(?:\[([^\]]+)\]|([^:]+)):(\d+)", value.strip())
    if match is None:
        raise DiscoveryError("bounded Ansible caddy_upstream must be host:port")
    host = match.group(1) or match.group(2)
    port = int(match.group(3))
    if not 1 <= port <= 65535:
        raise DiscoveryError("bounded Ansible caddy_upstream port must be between 1 and 65535")
    try:
        host = str(ipaddress.ip_address(host))
    except ValueError:
        normalized = host.lower().rstrip(".")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", normalized):
            raise DiscoveryError("bounded Ansible caddy_upstream host must be an IP address or hostname")
        host = normalized
    return {"host": host, "port": port}


def _normalize_caddy_extra_vhosts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise DiscoveryError("bounded Ansible caddy_extra_vhosts must be a list")
    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) not in ({"server_name", "upstream"}, {"server_names", "upstream"}):
            raise DiscoveryError("bounded Ansible caddy_extra_vhosts must use server_name(s) and upstream")
        names = item.get("server_names", item.get("server_name"))
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, list) or not names or not all(isinstance(name, str) and name.strip() for name in names):
            raise DiscoveryError("bounded Ansible caddy_extra_vhosts server_names must be a non-empty string list")
        normalized_names = [name.lower().rstrip(".") for name in names]
        if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", name) for name in normalized_names):
            raise DiscoveryError("bounded Ansible caddy_extra_vhosts server_names must be hostnames")
        if len(normalized_names) != len(set(normalized_names)):
            raise DiscoveryError("bounded Ansible caddy_extra_vhosts server_names must be unique")
        if seen_names & set(normalized_names):
            raise DiscoveryError("bounded Ansible caddy_extra_vhosts server_names must be unique")
        seen_names.update(normalized_names)
        normalized.append(
            {
                "server_names": normalized_names,
                "upstream": _normalize_caddy_upstream(item["upstream"]),
            }
        )
    return normalized


def _normalize_public_name(value: Any) -> Any:
    if isinstance(value, str):
        return [value.lower().rstrip(".")]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return [item.lower().rstrip(".") for item in value]
    return value


def _normalize_public_url(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        return value
    path = parsed.path.rstrip("/") + "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _normalize_port(value: Any) -> Any:
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return value


def _observe(
    source: str,
    key: str,
    value: Any,
    report: DiscoveryReport,
    migration: Any,
    proposed_path_override: str | None = None,
) -> None:
    classification, proposed_path = _classification(key, migration)
    if proposed_path_override is not None:
        proposed_path = proposed_path_override
    if classification == "secret":
        report.observations.append(FieldObservation(source, key, classification, None, type(value).__name__, "<redacted>"))
        return
    public = _public_value(value)
    if proposed_path in {
        "services.technitium.endpoints.public_names",
        "services.infisical.endpoints.public_names",
        "services.forgejo.endpoints.public_names",
        "services.hermes.endpoints.public_names",
        "services.technitium.configuration.caddy.server_names",
    }:
        public = _normalize_public_name(public)
    value_type = type(value).__name__
    if proposed_path == "services.technitium.configuration.caddy.upstream":
        public = _normalize_caddy_upstream(value)
    if proposed_path == "services.technitium.configuration.caddy.extra_vhosts":
        public = _normalize_caddy_extra_vhosts(value)
    if proposed_path in {
        "services.forgejo.endpoints.public_url",
        "services.technitium.configuration.api_url",
    }:
        public = _normalize_public_url(public)
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


def _read_site_metadata(path: Path, report: DiscoveryReport) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DiscoveryError(f"invalid site metadata: {path}") from error
    if not isinstance(value, dict):
        raise DiscoveryError(f"site metadata must be an object: {path}")
    allowed = ("name", "class", "lifecycle", "allow_apply", "allow_destroy")
    metadata = {key: value[key] for key in allowed if key in value}
    if any(not isinstance(item, (str, bool)) for item in metadata.values()):
        raise DiscoveryError(f"site metadata contains invalid scalar values: {path}")
    report.site_metadata = metadata


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


def _ansible_dynamic_reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", value.strip())
    return match.group(1) if match else None


def _ansible_value_type(value: Any) -> str:
    if isinstance(value, str) and ("{{" in value or "{%" in value):
        return "dynamic-expression"
    return type(value).__name__


def _read_ansible_bounded_slice(path: Path, report: DiscoveryReport, migration: Any) -> None:
    """Import only explicitly admitted, non-secret inventory fields.

    The adapter remains report-only and intentionally leaves all other inventory
    identities as residual unsupported observations. Each admitted family must
    be independently safe to normalize and compare with legacy sources.
    """
    allowed_keys = {
        "forgejo_actions_default_url",
        "FORGEJO_ACTIONS_DEFAULT_URL",
        "forgejo_actions_enabled",
        "FORGEJO_ACTIONS_ENABLED",
        "forgejo_bootstrap_enabled",
        "FORGEJO_BOOTSTRAP_ENABLED",
        "forgejo_bootstrap_admin_username",
        "forgejo_bootstrap_admin_email",
        "forgejo_bootstrap_owner_email",
        "forgejo_database",
        "onramp_host_password_authentication",
        "onramp_host_permit_root_login",
        "onramp_host_deploy_user",
        "onramp_host_deploy_dir",
        "onramp_host_allow_passwordless_sudo",
        "onramp_host_allowed_ssh_cidrs",
        "onramp_host_cloud_init_user",
        "onramp_host_ssh_public_keys",
        "tailscale_client_enabled",
        "hermes_ssh_public_keys",
        "searxng_server_name",
        "searxng_public_url",
        "searxng_container_image",
        "caddy_email",
        "caddy_server_name",
        "caddy_server_names",
        "caddy_upstream",
        "caddy_extra_vhosts",
        "forgejo_configure_system_ssh",
        "FORGEJO_CONFIGURE_SYSTEM_SSH",
        "forgejo_domain",
        "FORGEJO_DOMAIN",
        "forgejo_enable_caddy",
        "FORGEJO_ENABLE_CADDY",
        "forgejo_root_url",
        "FORGEJO_ROOT_URL",
        "tailscale_client_enable_ip_forwarding",
        "tailscale_client_restore_backup",
        "tailscale_client_backup_archive",
        "tailscale_client_up_args",
        "searxng_container_port",
        "searxng_bind_address",
        "searxng_instance_name",
        "searxng_enable_public_url",
        "forgejo_runner_version",
        "forgejo_runner_url",
        "forgejo_runner_name",
        "forgejo_runner_scope",
        "forgejo_runner_label",
        "forgejo_runner_labels",
        "forgejo_runner_hosts",
        "infisical_data_dir",
        "infisical_postgres_user",
        "infisical_postgres_db",
        "infisical_domain",
        "infisical_version",
        "infisical_vmid",
        "forgejo_runner_vmid",
        "forgejo_runner_dns_servers",
        "technitium_vmid",
        "forgejo_vmid",
        "tailscale_client_vmid",
        "infisical_vmid",
        "forgejo_runner_vmid",
        "hermes_vmid",
        "hermes_domain",
        "hermes_runtime_user",
        "hermes_repo_path",
        "hermes_vmid",
        "technitium_api_url",
        "technitium_admin_user",
        "hermes_discovery_version",
        "hermes_discovery_tag",
        "hermes_discovery_commit",
        "hermes_discovery_wheel_sha256",
        "hermes_node_version",
        "hermes_node_sha256_amd64",
        "hermes_node_sha256_arm64",
        "hermes_dashboard_enabled",
        "hermes_dashboard_port",
        "hermes_dashboard_host",
        "hermes_dashboard_basic_auth_username",
        "hermes_runtime_passwordless_sudo",
        "hermes_allow_legacy_runtime",
        "hermes_compression_threshold",
        "hermes_max_concurrent_children",
        "hermes_max_spawn_depth",
        "hermes_web_searxng_url",
        "hermes_control_enabled",
        "HERMES_CONTROL_SOURCE_URL",
        "HERMES_CONTROL_SOURCE_REF",
        "hermes_control_domain",
        "hermes_control_api_host",
        "hermes_control_api_port",
        "hermes_control_require_task_approval",
        "hermes_control_plugin_socket",
        "forgejo_ssh_port",
        "FORGEJO_SSH_PORT",
        "forgejo_version",
        "FORGEJO_VERSION",
        "forgejo_write_initial_config",
        "FORGEJO_WRITE_INITIAL_CONFIG",
        "technitium_discovery_version",
        "technitium_portable_sha256",
    }
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
    except (KeyError, TypeError) as error:
        raise DiscoveryError("bounded Ansible importer requires all.vars mapping") from error
    if not isinstance(variables, dict):
        raise DiscoveryError("bounded Ansible inventory vars must be a mapping")
    source = path.as_posix()
    for key in sorted(set(variables) & allowed_keys):
        value = variables[key]
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            dynamic_reference = _ansible_dynamic_reference(value)
            report.observations.append(
                FieldObservation(
                    source,
                    key,
                    "unsupported",
                    None,
                    "dynamic-expression",
                    None,
                    dynamic_reference,
                    dynamic_reference in variables if dynamic_reference else None,
                )
            )
            continue
        if key in {"onramp_host_password_authentication", "onramp_host_permit_root_login", "onramp_host_allow_passwordless_sudo"}:
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key in {"onramp_host_deploy_user", "onramp_host_cloud_init_user", "onramp_host_deploy_dir"}:
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        elif key == "onramp_host_allowed_ssh_cidrs":
            if not isinstance(value, list) or not value:
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty list of CIDRs")
            for cidr in value:
                try:
                    ipaddress.ip_network(cidr, strict=False)
                except (TypeError, ValueError) as error:
                    raise DiscoveryError(f"bounded Ansible {key} must contain valid CIDRs") from error
        elif key == "onramp_host_ssh_public_keys":
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                raise DiscoveryError(f"bounded Ansible {key} must be a list of strings with non-empty items")
        elif key == "caddy_server_name":
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", value.lower().rstrip(".")):
                raise DiscoveryError(f"bounded Ansible {key} must be a hostname")
        elif key == "caddy_server_names":
            normalized = [item.lower().rstrip(".") for item in value] if isinstance(value, list) and all(isinstance(item, str) for item in value) else []
            if not normalized or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", item) for item in normalized) or len(normalized) != len(set(normalized)):
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty list of unique hostnames")
        elif key == "caddy_email":
            if not isinstance(value, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+", value):
                raise DiscoveryError(f"bounded Ansible {key} must be an email address")
        elif key == "hermes_ssh_public_keys":
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                raise DiscoveryError(f"bounded Ansible {key} must be a list of strings with non-empty items")
        elif key in {"tailscale_client_up_args", "forgejo_runner_dns_servers"}:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise DiscoveryError(f"bounded Ansible {key} must be a list of strings")
        elif key == "infisical_data_dir":
            data_path: PurePosixPath | None = PurePosixPath(value) if isinstance(value, str) else None
            if data_path is None or not value.startswith("/") or ".." in data_path.parts:
                raise DiscoveryError(f"bounded Ansible {key} must be a normalized absolute POSIX path")
        elif key in {"infisical_postgres_user", "infisical_postgres_db"}:
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a PostgreSQL identifier")
        elif key == "infisical_domain":
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", value.lower().rstrip(".")):
                raise DiscoveryError(f"bounded Ansible {key} must be a hostname")
        elif key == "infisical_version":
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        elif key == "forgejo_runner_url":
            from urllib.parse import urlsplit

            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
        elif key in {"forgejo_runner_version", "forgejo_runner_name", "forgejo_runner_scope", "forgejo_runner_label"}:
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        elif key == "forgejo_runner_labels":
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty list of strings")
        elif key == "forgejo_runner_hosts":
            if not isinstance(value, list) or not all(
                isinstance(item, dict)
                and set(item) == {"name", "address"}
                and all(isinstance(item[field], str) and item[field].strip() for field in ("name", "address"))
                for item in value
            ):
                raise DiscoveryError(f"bounded Ansible {key} must be a list of name/address objects")
        elif key == "caddy_upstream":
            _normalize_caddy_upstream(value)
        elif key == "caddy_extra_vhosts":
            _normalize_caddy_extra_vhosts(value)
        elif key in {"forgejo_domain", "FORGEJO_DOMAIN"}:
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", value.lower().rstrip(".")):
                raise DiscoveryError(f"bounded Ansible {key} must be a hostname")
        elif key in {"forgejo_version", "FORGEJO_VERSION"}:
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        elif key in {"forgejo_enable_caddy", "FORGEJO_ENABLE_CADDY", "forgejo_configure_system_ssh", "FORGEJO_CONFIGURE_SYSTEM_SSH", "forgejo_write_initial_config", "FORGEJO_WRITE_INITIAL_CONFIG", "forgejo_bootstrap_enabled", "FORGEJO_BOOTSTRAP_ENABLED"}:
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key in {"forgejo_bootstrap_admin_username"}:
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a Linux user identifier")
        elif key in {"forgejo_bootstrap_admin_email", "forgejo_bootstrap_owner_email"}:
            if not isinstance(value, str) or not re.fullmatch(r"[^@\\s]+@[^@\\s]+", value):
                raise DiscoveryError(f"bounded Ansible {key} must be an email address")
        elif key == "forgejo_database":
            allowed = {"type", "managed", "host", "port", "name", "user", "ssl_mode"}
            valid = isinstance(value, dict) and set(value) <= allowed
            if valid:
                database_type = value.get("type")
                postgres_fields = {"managed", "host", "port", "name", "user", "ssl_mode"}
                if database_type == "postgres":
                    valid = {"name", "user"} <= set(value)
                elif database_type == "sqlite":
                    valid = not (set(value) & postgres_fields)
                if valid:
                    valid = all(
                        (field == "type" and item in {"sqlite", "postgres"})
                        or (field == "managed" and isinstance(item, bool))
                        or (field == "port" and isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= 65535)
                        or (field in {"host", "ssl_mode"} and isinstance(item, str) and item.strip())
                        or (field in {"name", "user"} and isinstance(item, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item))
                        for field, item in value.items()
                    )
            if not valid:
                raise DiscoveryError(f"bounded Ansible {key} must be valid database metadata")
        elif key in {"forgejo_root_url", "FORGEJO_ROOT_URL"}:
            from urllib.parse import urlsplit

            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
        elif key in {"forgejo_ssh_port", "FORGEJO_SSH_PORT"}:
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
                raise DiscoveryError(f"bounded Ansible {key} must be between 1 and 65535")
        elif key in {"forgejo_actions_enabled", "FORGEJO_ACTIONS_ENABLED"}:
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key in {"forgejo_actions_default_url", "FORGEJO_ACTIONS_DEFAULT_URL"}:
            from urllib.parse import urlsplit

            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
        elif key == "searxng_server_name":
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", value.lower().rstrip(".")):
                raise DiscoveryError(f"bounded Ansible {key} must be a hostname")
        elif key == "searxng_public_url":
            from urllib.parse import urlsplit

            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
        elif key == "searxng_instance_name":
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        elif key == "searxng_container_image":
            if not isinstance(value, str) or not re.fullmatch(
                r"[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}", value
            ):
                raise DiscoveryError(
                    f"bounded Ansible {key} must be an immutable repository@sha256:digest reference"
                )
        elif key == "searxng_container_port":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
                raise DiscoveryError(f"bounded Ansible {key} must be between 1 and 65535")
        elif key == "searxng_bind_address":
            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be a loopback IP address")
            try:
                address = ipaddress.ip_address(value)
            except ValueError as error:
                raise DiscoveryError(f"bounded Ansible {key} must be a loopback IP address") from error
            if not address.is_loopback:
                raise DiscoveryError(f"bounded Ansible {key} must be a loopback IP address")
        elif key == "searxng_enable_public_url":
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key in {"tailscale_client_enabled", "tailscale_client_restore_backup", "tailscale_client_enable_ip_forwarding"}:
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key == "tailscale_client_backup_archive":
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        elif key in {
            "technitium_vmid",
            "forgejo_vmid",
            "tailscale_client_vmid",
            "infisical_vmid",
            "forgejo_runner_vmid",
            "hermes_vmid",
        }:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise DiscoveryError(f"bounded Ansible {key} must be a positive integer")
        elif key in {"forgejo_ssh_port", "FORGEJO_SSH_PORT"}:
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
                raise DiscoveryError(f"bounded Ansible {key} must be between 1 and 65535")
        elif key in {"forgejo_actions_enabled", "FORGEJO_ACTIONS_ENABLED"}:
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key in {"forgejo_actions_default_url", "FORGEJO_ACTIONS_DEFAULT_URL"}:
            from urllib.parse import urlsplit

            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials")
        elif key == "technitium_api_url":
            from urllib.parse import urlsplit

            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTP(S) URL without credentials")
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTP(S) URL without credentials")
        elif key == "HERMES_CONTROL_SOURCE_URL":
            from urllib.parse import urlsplit

            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials or fragments")
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTPS URL without credentials or fragments")
        elif key == "HERMES_CONTROL_SOURCE_REF":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a lowercase 40-character commit")
        elif key == "hermes_domain":
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", value.lower().rstrip(".")):
                raise DiscoveryError(f"bounded Ansible {key} must be a hostname")
        elif key == "hermes_runtime_user":
            if not isinstance(value, str) or value == "root" or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a non-root Linux user identifier")
        elif key == "hermes_repo_path":
            repo_path: PurePosixPath | None = PurePosixPath(value) if isinstance(value, str) else None
            if (
                repo_path is None
                or not value.startswith("/")
                or value != str(repo_path)
                or any(part in {"", ".", ".."} for part in repo_path.parts)
            ):
                raise DiscoveryError(f"bounded Ansible {key} must be a normalized absolute POSIX path")
        elif key == "hermes_control_enabled":
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key in {"hermes_runtime_passwordless_sudo", "hermes_allow_legacy_runtime"}:
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key in {
            "hermes_compression_threshold",
            "hermes_max_concurrent_children",
            "hermes_max_spawn_depth",
        }:
            bounds = {
                "hermes_compression_threshold": (0.5, 0.95),
                "hermes_max_concurrent_children": (1, 10),
                "hermes_max_spawn_depth": (1, 3),
            }
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not bounds[key][0] <= value <= bounds[key][1]
                or (key != "hermes_compression_threshold" and not isinstance(value, int))
            ):
                raise DiscoveryError(f"bounded Ansible {key} is outside its canonical range")
        elif key == "hermes_web_searxng_url":
            from urllib.parse import urlsplit

            if not isinstance(value, str):
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTP(S) URL without credentials")
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise DiscoveryError(f"bounded Ansible {key} must be an HTTP(S) URL without credentials")
        elif key == "hermes_control_domain":
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?", value.lower().rstrip(".")):
                raise DiscoveryError(f"bounded Ansible {key} must be a hostname")
        elif key == "hermes_control_api_host":
            if value != "127.0.0.1":
                raise DiscoveryError(f"bounded Ansible {key} must be 127.0.0.1")
        elif key == "hermes_control_plugin_socket":
            socket_path: PurePosixPath | None = PurePosixPath(value) if isinstance(value, str) else None
            if (
                socket_path is None
                or not value.startswith("/")
                or value != str(socket_path)
                or any(part in {"", ".", ".."} for part in socket_path.parts)
            ):
                raise DiscoveryError(f"bounded Ansible {key} must be a normalized absolute POSIX path")
        elif key in {"hermes_control_domain", "hermes_control_api_host", "hermes_control_plugin_socket"}:
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        elif key == "hermes_control_api_port":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
                raise DiscoveryError(f"bounded Ansible {key} must be between 1 and 65535")
        elif key == "hermes_control_require_task_approval":
            if value is not True:
                raise DiscoveryError(f"bounded Ansible {key} must be true")
        elif key == "hermes_dashboard_enabled":
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif key == "hermes_dashboard_port":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
                raise DiscoveryError(f"bounded Ansible {key} must be between 1 and 65535")
        elif key == "hermes_dashboard_host":
            if value not in {"127.0.0.1", "::1", "localhost"}:
                raise DiscoveryError(f"bounded Ansible {key} must be loopback-only")
        elif key == "hermes_dashboard_basic_auth_username":
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        elif key == "hermes_node_version":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a strict semantic version")
        elif key in {"hermes_node_sha256_amd64", "hermes_node_sha256_arm64"}:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a lowercase 64-character SHA-256 digest")
        elif key == "hermes_discovery_version":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a strict semantic version")
        elif key == "hermes_discovery_tag":
            if not isinstance(value, str) or not re.fullmatch(r"v[0-9]{4}\.[0-9]+\.[0-9]+(?:\.[0-9]+)?", value):
                raise DiscoveryError(f"bounded Ansible {key} must use the managed Hermes release-tag form")
        elif key == "hermes_discovery_commit":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a lowercase 40-character commit")
        elif key == "hermes_discovery_wheel_sha256":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a lowercase 64-character SHA-256 digest")
        elif key == "technitium_admin_user":
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a Linux user identifier")
        elif key == "technitium_discovery_version":
            if not isinstance(value, str) or not value.strip():
                raise DiscoveryError(f"bounded Ansible {key} must be a non-empty version")
        elif key == "technitium_portable_sha256":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
                raise DiscoveryError(f"bounded Ansible {key} must be a 64-character SHA-256 digest")
        elif key in {"tailscale_client_enable_ip_forwarding", "tailscale_client_restore_backup"}:
            if not isinstance(value, bool):
                raise DiscoveryError(f"bounded Ansible {key} must be boolean")
        elif not isinstance(value, (str, bool, int, float)):
            raise DiscoveryError(f"bounded Ansible {key} must be a scalar")
        if isinstance(value, str) and not value.strip():
            raise DiscoveryError(f"bounded Ansible {key} must be a non-empty string")
        _observe(
            source,
            key,
            value,
            report,
            migration,
            "services.technitium.configuration.api_url"
            if key == "technitium_api_url"
            else None,
        )
    protected_provider_keys = {"CF_API_EMAIL"}
    secret_provider_keys = {"caddy_cloudflare_api_token", "CF_DNS_API_TOKEN"}
    for key in sorted(set(variables) - allowed_keys):
        classification, _ = _classification(key, migration)
        if key in protected_provider_keys:
            classification = "protected"
        elif key in secret_provider_keys:
            classification = "secret"
        observation_classification = (
            "secret"
            if classification == "secret"
            else "protected"
            if classification == "protected"
            else "unsupported"
        )
        report.observations.append(
            FieldObservation(
                source,
                key,
                observation_classification,
                None,
                _ansible_value_type(variables[key]),
                "<redacted>" if classification in {"secret", "protected"} else None,
            )
        )


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
    site_metadata = values / "site.json"
    if site_metadata.is_file():
        report.files.append(site_metadata.relative_to(values).as_posix())
        _read_site_metadata(site_metadata, report)
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
        _read_ansible_bounded_slice(inventory, report, migration)
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
        "site_metadata": report.site_metadata,
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
