#!/usr/bin/env python3
"""Strict loader and identity helpers for canonical site values.

This module intentionally owns only the public, non-secret site model. Secret
loading and consumer projections are separate phases of the migration.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError, field_validator, model_validator
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.parser import ParserError
from ruamel.yaml.tokens import AliasToken, AnchorToken

from service_catalog import ServiceCatalogError, load_catalog


class CanonicalValuesError(ValueError):
    """Raised when a canonical site document cannot be safely loaded."""


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_HOSTNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,253}[a-z0-9])?$")
_PORT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_CIDR_RE = re.compile(r"^(?:dhcp|(?:[0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2})$")
_MAC_RE = re.compile(r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHECKSUM_RE = re.compile(r"^[0-9a-fA-F]{64}|[0-9a-fA-F]{128}$")
_HERMES_TAG_RE = re.compile(r"^v[0-9]{4}\.[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
_HERMES_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_HERMES_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_HERMES_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def normalize_container_image_reference(reference: str) -> tuple[str, str]:
    """Split an immutable lowercase container reference into image and digest."""
    if not isinstance(reference, str) or reference != reference.strip() or reference.count("@") != 1:
        raise CanonicalValuesError("container image must use repository@sha256:digest")
    image, digest = reference.split("@", 1)
    if not image or image != image.lower() or any(char.isspace() for char in image):
        raise CanonicalValuesError("container image repository must be lowercase and non-empty")
    if not _DIGEST_RE.fullmatch(digest):
        raise CanonicalValuesError("container image digest must be lowercase sha256")
    return image, digest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SiteMetadata(StrictModel):
    name: StrictStr
    class_: StrictStr = Field(alias="class")
    lifecycle: Literal["disposable", "persistent", "protected"]
    allow_apply: StrictBool
    allow_destroy: StrictBool

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError("site.name must be a lowercase DNS-safe identifier")
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> "SiteMetadata":
        if self.class_ == "production" and self.lifecycle == "disposable":
            raise ValueError("production sites cannot use disposable lifecycle")
        if self.class_ == "production" and self.allow_destroy:
            raise ValueError("production sites cannot allow destroy")
        if self.lifecycle == "protected" and (self.allow_apply or self.allow_destroy):
            raise ValueError("protected sites cannot allow apply or destroy")
        return self


class ProxmoxPlatform(StrictModel):
    endpoint: StrictStr
    node: StrictStr
    insecure: StrictBool = False


class NetworkDefaults(StrictModel):
    default_bridge: StrictStr | None = None
    default_gateway: StrictStr | None = None
    default_dns_servers: list[StrictStr] = Field(default_factory=list)
    default_search_domain: StrictStr | None = None
    default_vlan_id: StrictInt | None = None


class StorageDefaults(StrictModel):
    rootfs_datastore: StrictStr
    template_datastore: StrictStr
    backup_datastore: StrictStr | None = None


class ImageChecksum(StrictModel):
    algorithm: Literal["sha256", "sha512"]
    value: StrictStr

    @field_validator("value")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        if not _CHECKSUM_RE.fullmatch(value):
            raise ValueError("checksum must be a SHA-256 or SHA-512 hexadecimal digest")
        return value.lower()

    @model_validator(mode="after")
    def validate_algorithm_length(self) -> "ImageChecksum":
        expected = 64 if self.algorithm == "sha256" else 128
        if len(self.value) != expected:
            raise ValueError(f"{self.algorithm} checksum must contain {expected} hex characters")
        return self


class ImageDefinition(StrictModel):
    type: Literal["lxc_template", "vm_image"]
    datastore_id: StrictStr | None = None
    url: StrictStr
    file_name: StrictStr
    checksum: ImageChecksum

    @model_validator(mode="after")
    def validate_datastore_ownership(self) -> "ImageDefinition":
        if self.type == "vm_image" and not self.datastore_id:
            raise ValueError("vm images require datastore_id ownership")
        if self.type == "lxc_template" and self.datastore_id is not None:
            raise ValueError("lxc templates use platform storage template_datastore")
        return self

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("image url must be an HTTPS URL without credentials or fragments")
        return value

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\\\" in value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", value):
            raise ValueError("image file_name must be a safe pathless filename")
        return value


class PlatformImages(StrictModel):
    lxc: dict[str, ImageDefinition] = Field(default_factory=dict)
    vm: dict[str, ImageDefinition] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_image_keys(self) -> "PlatformImages":
        for family, definitions, expected_type in (
            ("lxc", self.lxc, "lxc_template"),
            ("vm", self.vm, "vm_image"),
        ):
            for name, definition in definitions.items():
                if not _IDENTIFIER_RE.fullmatch(name):
                    raise ValueError(f"platform.images.{family} keys must be lowercase identifiers")
                if definition.type != expected_type:
                    raise ValueError(f"platform.images.{family}.{name} type does not match its image family")
        return self


class Platform(StrictModel):
    proxmox: ProxmoxPlatform
    network: NetworkDefaults
    storage: StorageDefaults
    vm_cloud_init_user: StrictStr | None = None
    lxc_template_download_timeout_seconds: StrictInt | None = None
    images: PlatformImages = Field(default_factory=PlatformImages)

    @field_validator("vm_cloud_init_user")
    @classmethod
    def validate_vm_cloud_init_user(cls, value: str | None) -> str | None:
        if value is not None and not _HERMES_USER_RE.fullmatch(value):
            raise ValueError("platform.vm_cloud_init_user must be a valid Linux user identifier")
        return value

    @field_validator("lxc_template_download_timeout_seconds")
    @classmethod
    def validate_lxc_template_download_timeout(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("platform.lxc_template_download_timeout_seconds must be positive")
        return value


class ResourceIdentity(StrictModel):
    vmid: StrictInt
    hostname: StrictStr
    description: StrictStr | None = None

    @field_validator("vmid")
    @classmethod
    def validate_vmid(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("resource identity.vmid must be positive")
        return value

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        normalized = value.lower().rstrip(".")
        if not _HOSTNAME_RE.fullmatch(normalized):
            raise ValueError("resource identity.hostname must be a valid hostname")
        return normalized


class ResourceNetwork(StrictModel):
    address: StrictStr
    expected_address: StrictStr | None = None
    gateway: StrictStr | None = None
    mac_address: StrictStr | None = None
    bridge: StrictStr | None = None
    vlan_id: StrictInt | None = None
    dns_servers: list[StrictStr] = Field(default_factory=list)
    search_domain: StrictStr | None = None

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str) -> str:
        if not _CIDR_RE.fullmatch(value):
            raise ValueError("network.address must be dhcp or an IPv4 CIDR")
        return value

    @field_validator("expected_address")
    @classmethod
    def validate_expected_address(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as error:
                raise ValueError("network.expected_address must be an IPv4 address") from error
            if address.version != 4:
                raise ValueError("network.expected_address must be an IPv4 address")
        return value

    @field_validator("gateway")
    @classmethod
    def validate_gateway(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as error:
                raise ValueError("network.gateway must be an IPv4 address") from error
            if address.version != 4:
                raise ValueError("network.gateway must be an IPv4 address")
        return value

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, value: str | None) -> str | None:
        if value is not None:
            if not _MAC_RE.fullmatch(value):
                raise ValueError("network.mac_address must be six colon-separated hexadecimal octets")
            return value.lower()
        return value

    @model_validator(mode="after")
    def validate_dhcp_policy(self) -> "ResourceNetwork":
        if self.address == "dhcp" and self.gateway is not None:
            raise ValueError("DHCP resources cannot declare a static gateway")
        if self.address != "dhcp" and self.expected_address is not None:
            raise ValueError("static resources cannot declare expected_address")
        return self


class ResourceCompute(StrictModel):
    cores: StrictInt
    memory_mb: StrictInt
    swap_mb: StrictInt = 0

    @model_validator(mode="after")
    def validate_sizes(self) -> "ResourceCompute":
        if self.cores <= 0 or self.memory_mb <= 0 or self.swap_mb < 0:
            raise ValueError("resource compute values must be positive, with non-negative swap")
        return self


class ResourceVolume(StrictModel):
    type: Literal["proxmox_volume", "directory", "bind"]
    storage_id: StrictStr | None = None
    size_gb: StrictInt | None = None
    target: StrictStr
    backup: StrictBool = True

    @field_validator("size_gb")
    @classmethod
    def validate_size(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("storage volume size_gb must be positive")
        return value


class ResourceStorage(StrictModel):
    root: ResourceVolume
    volumes: dict[str, ResourceVolume] = Field(default_factory=dict)


class ResourceRuntime(StrictModel):
    started: StrictBool = True
    start_on_boot: StrictBool = True
    cloud_init_user: StrictStr | None = None

    @field_validator("cloud_init_user")
    @classmethod
    def validate_cloud_init_user(cls, value: str | None) -> str | None:
        if value is not None and not _HERMES_USER_RE.fullmatch(value):
            raise ValueError("resource runtime.cloud_init_user must be a valid Linux user identifier")
        return value
    unprivileged: StrictBool | None = None
    nesting: StrictBool | None = None
    features: dict[str, StrictBool] = Field(default_factory=dict)
    template: dict[str, StrictStr] | None = None
    firmware: Literal["uefi", "seabios"] | None = None
    machine: StrictStr | None = None
    guest_agent: StrictBool | None = None
    cloud_init: dict[str, Any] | None = None
    users: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ResourceSecurity(StrictModel):
    password_authentication: StrictBool | None = None
    permit_root_login: StrictBool | None = None
    deploy_user: StrictStr | None = None
    deploy_dir: StrictStr | None = None
    allow_passwordless_sudo: StrictBool | None = None
    allowed_ssh_cidrs: list[StrictStr] = Field(default_factory=list)
    ssh_public_keys: list[StrictStr] = Field(default_factory=list)


class Resource(StrictModel):
    type: Literal["lxc", "vm"]
    identity: ResourceIdentity
    network: ResourceNetwork
    compute: ResourceCompute
    storage: ResourceStorage
    runtime: ResourceRuntime
    security: ResourceSecurity = Field(default_factory=ResourceSecurity)

    @model_validator(mode="after")
    def validate_runtime_fields(self) -> "Resource":
        runtime = self.runtime
        if self.type == "lxc" and any(value is not None for value in (runtime.firmware, runtime.machine, runtime.guest_agent, runtime.cloud_init)):
            raise ValueError("VM-only runtime fields are not valid on LXC resources")
        if self.type == "vm" and any(value is not None for value in (runtime.unprivileged, runtime.nesting)):
            raise ValueError("LXC-only runtime fields are not valid on VM resources")
        return self


class Resources(StrictModel):
    guests: dict[str, Resource] = Field(default_factory=dict)
    shared_hosts: dict[str, Resource] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ids(self) -> "Resources":
        all_items = [*self.guests.items(), *self.shared_hosts.items()]
        names = [name for name, _ in all_items]
        if len(names) != len(set(names)):
            raise ValueError("resource identifiers must be unique across guests and shared_hosts")
        vmids = [resource.identity.vmid for _, resource in all_items]
        if len(vmids) != len(set(vmids)):
            raise ValueError("resource VMIDs must be unique")
        hostnames = [resource.identity.hostname for _, resource in all_items]
        if len(hostnames) != len(set(hostnames)):
            raise ValueError("resource hostnames must be unique")
        networks = []
        for name, resource in all_items:
            if resource.network.address == "dhcp":
                continue
            try:
                network = ipaddress.ip_network(resource.network.address, strict=False)
            except ValueError as error:
                raise ValueError(f"resources.{name}.network.address must be a valid IPv4 CIDR") from error
            if network.version != 4:
                raise ValueError(f"resources.{name}.network.address must be an IPv4 CIDR")
            for other_name, other_network in networks:
                if network.overlaps(other_network):
                    raise ValueError(
                        f"resource network ranges overlap: {name} ({network}) and {other_name} ({other_network})"
                    )
            networks.append((name, network))
        return self


class ForgejoDatabaseConfiguration(StrictModel):
    """Non-secret Forgejo database selection and connection metadata."""

    type: Literal["sqlite", "postgres"] = "sqlite"
    managed: StrictBool = True
    host: StrictStr = "127.0.0.1"
    port: StrictInt = 5432
    name: StrictStr = "forgejo"
    user: StrictStr = "forgejo"
    ssl_mode: StrictStr = "disable"

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("Forgejo database port must be between 1 and 65535")
        return value

    @model_validator(mode="after")
    def validate_postgres_identifiers(self) -> "ForgejoDatabaseConfiguration":
        if self.type == "postgres":
            identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
            if not identifier.fullmatch(self.name) or not identifier.fullmatch(self.user):
                raise ValueError("PostgreSQL Forgejo database name and user must be SQL identifiers")
        return self


class SearxngConfiguration(StrictModel):
    """Typed non-secret SearXNG host publication and instance settings."""

    container_port: StrictInt | None = None
    bind_address: StrictStr | None = None
    instance_name: StrictStr | None = None
    enable_public_url: StrictBool | None = None

    @field_validator("container_port")
    @classmethod
    def validate_container_port(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 65535:
            raise ValueError("SearXNG container port must be between 1 and 65535")
        return value

    @field_validator("bind_address")
    @classmethod
    def validate_bind_address(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as error:
                raise ValueError("SearXNG bind address must be an IP address") from error
            if address.is_unspecified or not address.is_loopback:
                raise ValueError("SearXNG bind address must be loopback-only")
        return value


class ForgejoRunnerHost(StrictModel):
    name: StrictStr
    address: StrictStr


class ForgejoRunnerConfiguration(StrictModel):
    """Typed non-secret Forgejo Runner registration metadata."""

    url: StrictStr | None = None
    name: StrictStr | None = None
    scope: StrictStr | None = None
    label: StrictStr | None = None
    labels: list[StrictStr] | None = None
    hosts: list[ForgejoRunnerHost] | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("Forgejo Runner URL must be HTTPS without credentials")
        return value


class TailscaleConfiguration(StrictModel):
    """Typed non-secret Tailscale restore and networking behavior."""

    restore_backup: StrictBool | None = None
    backup_archive: StrictStr | None = None
    enable_ip_forwarding: StrictBool | None = None
    up_args: list[StrictStr] | None = None


class InfisicalConfiguration(StrictModel):
    """Typed non-secret Infisical storage and database identity settings."""

    data_dir: StrictStr | None = None
    postgres_user: StrictStr | None = None
    postgres_db: StrictStr | None = None


class ForgejoConfiguration(StrictModel):
    """Typed non-secret Forgejo role configuration."""

    database: ForgejoDatabaseConfiguration = Field(default_factory=ForgejoDatabaseConfiguration)
    enable_caddy: StrictBool | None = None
    configure_system_ssh: StrictBool | None = None
    write_initial_config: StrictBool | None = None
    bootstrap_enabled: StrictBool | None = None
    bootstrap_admin_username: StrictStr | None = None
    bootstrap_admin_email: StrictStr | None = None
    bootstrap_owner_email: StrictStr | None = None
    actions_enabled: StrictBool | None = None
    actions_default_url: StrictStr | None = None

    @field_validator("actions_default_url")
    @classmethod
    def validate_actions_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("Forgejo Actions default URL must be an HTTPS URL without credentials")
        return value


class ServiceState(StrictModel):
    capable: StrictBool = False
    backup: dict[str, Any] = Field(default_factory=dict)
    disable_policy: Literal["retain", "archive", "destroy"] | None = None


class ServiceEndpointDNS(StrictModel):
    enabled: StrictBool = False
    record_type: Literal["A"] = "A"


class ServiceEndpoints(StrictModel):
    public_names: list[StrictStr] = Field(default_factory=list)
    public_url: StrictStr | None = None
    protocols: list[StrictStr] = Field(default_factory=list)
    ports: dict[str, StrictInt] = Field(default_factory=dict)
    visibility: Literal["internal", "public", "none"] = "internal"
    dns: ServiceEndpointDNS = Field(default_factory=ServiceEndpointDNS)

    @field_validator("public_names")
    @classmethod
    def validate_names(cls, value: list[str]) -> list[str]:
        normalized = [name.lower().rstrip(".") for name in value]
        if any(not _HOSTNAME_RE.fullmatch(name) for name in normalized):
            raise ValueError("service endpoint public_names must contain valid hostnames")
        if len(normalized) != len(set(normalized)):
            raise ValueError("service endpoint public_names must be unique")
        return normalized

    @field_validator("protocols")
    @classmethod
    def validate_protocols(cls, value: list[str]) -> list[str]:
        normalized = [protocol.lower() for protocol in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("service endpoint protocols must be unique")
        return normalized

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not _PORT_NAME_RE.fullmatch(name) for name in value):
            raise ValueError("service endpoint port names must be lowercase identifiers")
        if any(port < 1 or port > 65535 for port in value.values()):
            raise ValueError("service endpoint ports must be between 1 and 65535")
        return value


class ServiceRelease(StrictModel):
    version: StrictStr | None = None
    tag: StrictStr | None = None
    commit: StrictStr | None = None
    image: StrictStr | None = None
    digest: StrictStr | None = None
    checksum: StrictStr | None = None
    source: Literal["package", "container", "binary", "image"] | None = None

    @model_validator(mode="after")
    def validate_release(self) -> "ServiceRelease":
        if self.tag is not None and not _HERMES_TAG_RE.fullmatch(self.tag):
            raise ValueError("release tag must use the managed Hermes release-tag form")
        if self.commit is not None and not _HERMES_COMMIT_RE.fullmatch(self.commit):
            raise ValueError("release commit must be a lowercase 40-character commit")
        if self.source == "container":
            if not self.image or not self.digest:
                raise ValueError("container releases require image and immutable digest")
            if "@" in self.image or not _DIGEST_RE.fullmatch(self.digest):
                raise ValueError("container releases require a separate lowercase sha256 digest")
        if self.source in {"package", "binary"} and not self.version:
            raise ValueError(f"{self.source} releases require version")
        if self.source == "package" and self.digest:
            raise ValueError("package releases cannot declare digest")
        return self


class HermesRuntimeNode(StrictModel):
    version: StrictStr | None = None
    checksums: dict[Literal["amd64", "arm64"], StrictStr] = Field(default_factory=dict)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str | None) -> str | None:
        if value is not None and not _HERMES_VERSION_RE.fullmatch(value):
            raise ValueError("Hermes Node version must be a strict semantic version")
        return value

    @field_validator("checksums")
    @classmethod
    def validate_checksums(cls, value: dict[str, str]) -> dict[str, str]:
        for architecture, checksum in value.items():
            if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise ValueError(f"Hermes Node {architecture} checksum must be lowercase SHA-256")
        return value


class HermesTuning(StrictModel):
    compression_threshold: float | None = None
    max_concurrent_children: StrictInt | None = None
    max_spawn_depth: StrictInt | None = None

    @field_validator("compression_threshold")
    @classmethod
    def validate_threshold(cls, value: float | None) -> float | None:
        if value is not None and not 0.5 <= value <= 0.95:
            raise ValueError("Hermes compression threshold must be between 0.5 and 0.95")
        return value

    @field_validator("max_concurrent_children")
    @classmethod
    def validate_concurrency(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 10:
            raise ValueError("Hermes max_concurrent_children must be between 1 and 10")
        return value

    @field_validator("max_spawn_depth")
    @classmethod
    def validate_spawn_depth(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 3:
            raise ValueError("Hermes max_spawn_depth must be between 1 and 3")
        return value


class HermesDashboard(StrictModel):
    enabled: StrictBool | None = None
    host: StrictStr | None = None
    auth_username: StrictStr | None = None

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str | None) -> str | None:
        if value is not None and value not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("Hermes dashboard host must be loopback-only")
        return value


class HermesWebConfiguration(StrictModel):
    searxng_url: StrictStr | None = None


class HermesControlConfiguration(StrictModel):
    enabled: StrictBool = False
    domain: StrictStr | None = None
    source_url: StrictStr | None = None
    source_ref: StrictStr | None = None
    api_host: StrictStr = "127.0.0.1"
    api_port: StrictInt = 8787
    require_task_approval: StrictBool = True
    plugin_socket: StrictStr = "/run/hermes/control-extension.sock"

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower().rstrip(".")
        if not _HOSTNAME_RE.fullmatch(normalized):
            raise ValueError("Hermes Control domain must be a hostname")
        return normalized

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Hermes Control source_url must be HTTPS without credentials or fragments")
        return value

    @field_validator("source_ref")
    @classmethod
    def validate_source_ref(cls, value: str | None) -> str | None:
        if value is not None and not _HERMES_COMMIT_RE.fullmatch(value):
            raise ValueError("Hermes Control source_ref must be a lowercase 40-character commit")
        return value

    @field_validator("api_host")
    @classmethod
    def validate_api_host(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("Hermes Control api_host must be 127.0.0.1")
        return value

    @field_validator("api_port")
    @classmethod
    def validate_api_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("Hermes Control api_port must be between 1 and 65535")
        return value

    @field_validator("require_task_approval")
    @classmethod
    def validate_task_approval(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Hermes Control requires task approval")
        return value

    @field_validator("plugin_socket")
    @classmethod
    def validate_plugin_socket(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not value.startswith("/") or value != str(path) or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Hermes Control plugin_socket must be a normalized absolute POSIX path")
        return value

    @model_validator(mode="after")
    def validate_enabled_requirements(self) -> "HermesControlConfiguration":
        if self.enabled:
            missing = [name for name, value in (("domain", self.domain), ("source_url", self.source_url), ("source_ref", self.source_ref)) if not value]
            if missing:
                raise ValueError(f"enabled Hermes Control requires: {', '.join(missing)}")
        return self


class HermesConfiguration(StrictModel):
    runtime_user: StrictStr | None = None
    repository_path: StrictStr | None = None
    allow_legacy_runtime: StrictBool | None = None
    tuning: HermesTuning = Field(default_factory=HermesTuning)
    node: HermesRuntimeNode = Field(default_factory=HermesRuntimeNode)
    dashboard: HermesDashboard = Field(default_factory=HermesDashboard)
    web: HermesWebConfiguration = Field(default_factory=HermesWebConfiguration)
    control: HermesControlConfiguration = Field(default_factory=HermesControlConfiguration)

    @field_validator("runtime_user")
    @classmethod
    def validate_runtime_user(cls, value: str | None) -> str | None:
        if value is not None and (value == "root" or not _HERMES_USER_RE.fullmatch(value)):
            raise ValueError("Hermes runtime_user must be a non-root Linux user identifier")
        return value

    @field_validator("repository_path")
    @classmethod
    def validate_repository_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = PurePosixPath(value)
        if not value.startswith("/") or value != str(path) or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Hermes repository_path must be a normalized absolute POSIX path")
        return value


class Service(StrictModel):
    enabled: StrictBool
    resource: StrictStr | None = None
    dependencies: list[StrictStr] = Field(default_factory=list)
    state: ServiceState = Field(default_factory=ServiceState)
    endpoints: ServiceEndpoints = Field(default_factory=ServiceEndpoints)
    release: ServiceRelease = Field(default_factory=ServiceRelease)
    configuration: dict[str, Any] = Field(default_factory=dict)
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CanonicalSite(StrictModel):
    schema_version: Literal[1]
    site: SiteMetadata
    platform: Platform
    resources: Resources
    services: dict[str, Service]

    @model_validator(mode="after")
    def validate_service_ownership(self) -> "CanonicalSite":
        hermes = self.services.get("hermes")
        if hermes is not None:
            try:
                validated_hermes = HermesConfiguration.model_validate(hermes.configuration)
                hermes.configuration = validated_hermes.model_dump(mode="json", exclude_none=True)
            except ValidationError as error:
                details = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
                raise ValueError(f"services.hermes.configuration: {details}") from error
        searxng = self.services.get("searxng_onramp")
        if searxng is not None:
            try:
                configuration = SearxngConfiguration.model_validate(searxng.configuration)
                searxng.configuration = configuration.model_dump(mode="json", exclude_none=False)
            except ValidationError as error:
                details = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
                raise ValueError(f"services.searxng_onramp.configuration: {details}") from error
        runner = self.services.get("forgejo_runner")
        if runner is not None:
            try:
                configuration = ForgejoRunnerConfiguration.model_validate(runner.configuration)
                runner.configuration = configuration.model_dump(mode="json", exclude_none=False)
            except ValidationError as error:
                details = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
                raise ValueError(f"services.forgejo_runner.configuration: {details}") from error
        tailscale = self.services.get("tailscale_client")
        if tailscale is not None:
            try:
                configuration = TailscaleConfiguration.model_validate(tailscale.configuration)
                tailscale.configuration = configuration.model_dump(mode="json", exclude_none=False)
            except ValidationError as error:
                details = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
                raise ValueError(f"services.tailscale_client.configuration: {details}") from error
        infisical = self.services.get("infisical")
        if infisical is not None:
            try:
                configuration = InfisicalConfiguration.model_validate(infisical.configuration)
                infisical.configuration = configuration.model_dump(mode="json", exclude_none=False)
            except ValidationError as error:
                details = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
                raise ValueError(f"services.infisical.configuration: {details}") from error
        forgejo = self.services.get("forgejo")
        if forgejo is not None:
            try:
                configuration = ForgejoConfiguration.model_validate(forgejo.configuration)
                forgejo.configuration = configuration.model_dump(mode="json", exclude_none=False)
            except ValidationError as error:
                details = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
                raise ValueError(f"services.forgejo.configuration: {details}") from error
        for _, resource in (*self.resources.guests.items(), *self.resources.shared_hosts.items()):
            network = resource.network
            if network.bridge is None:
                network.bridge = self.platform.network.default_bridge
            if network.dns_servers == []:
                network.dns_servers = list(self.platform.network.default_dns_servers)
            if network.search_domain is None:
                network.search_domain = self.platform.network.default_search_domain
            if network.vlan_id is None:
                network.vlan_id = self.platform.network.default_vlan_id
            if network.address != "dhcp" and network.gateway is None:
                network.gateway = self.platform.network.default_gateway
            if resource.storage.root.storage_id is None:
                resource.storage.root.storage_id = self.platform.storage.rootfs_datastore
        resource_names = set(self.resources.guests) | set(self.resources.shared_hosts)
        for name, service in self.services.items():
            if service.enabled and service.resource is None:
                raise ValueError(f"services.{name}.resource is required when enabled")
            if service.resource is not None and service.resource not in resource_names:
                raise ValueError(f"services.{name}.resource does not resolve to a resource")
            if service.state.capable and service.state.disable_policy is None:
                raise ValueError(f"services.{name}.state.disable_policy is required when state-capable")
        return self


def _yaml_data(path: Path) -> dict[str, Any]:
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for token in yaml.scan(handle):
                if isinstance(token, (AliasToken, AnchorToken)):
                    raise CanonicalValuesError(f"YAML anchors and aliases are not permitted: {path}")
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle)
    except (DuplicateKeyError, ParserError, ValueError) as error:
        raise CanonicalValuesError(f"invalid canonical YAML: {path}: {error}") from error
    if not isinstance(data, dict):
        raise CanonicalValuesError(f"canonical site document must be a mapping: {path}")
    return data


def load_site(
    path: Path,
    *,
    expected_site: str | None = None,
    catalog_path: Path | None = None,
) -> CanonicalSite:
    """Load and strictly validate a canonical site YAML document."""
    try:
        model = CanonicalSite.model_validate(_yaml_data(path))
    except ValidationError as error:
        details = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
        raise CanonicalValuesError(f"invalid canonical site model {path}: {details}") from error
    directory_site = path.parent.name
    if model.site.name != directory_site:
        raise CanonicalValuesError(f"site.name {model.site.name!r} does not match directory {directory_site!r}")
    if expected_site is not None and model.site.name != expected_site:
        raise CanonicalValuesError(f"site.name {model.site.name!r} does not match selected site {expected_site!r}")
    if catalog_path is not None:
        try:
            catalog = load_catalog(catalog_path)
            catalog.validate_model_services(model.services, model.resources)
            catalog.validate_selection({name for name, service in model.services.items() if service.enabled})
        except ServiceCatalogError as error:
            raise CanonicalValuesError(str(error)) from error
    return model


def normalized_model(model: CanonicalSite) -> dict[str, Any]:
    """Return a stable, JSON-compatible representation for identity hashing."""
    return model.model_dump(mode="json", by_alias=True, exclude_none=False)


def model_digest(model: CanonicalSite) -> str:
    payload = json.dumps(normalized_model(model), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def redacted_summary(model: CanonicalSite) -> dict[str, Any]:
    return {
        "schema_version": model.schema_version,
        "site": model.site.model_dump(mode="json", by_alias=True),
        "resource_count": len(model.resources.guests) + len(model.resources.shared_hosts),
        "resources": [*model.resources.guests, *model.resources.shared_hosts],
        "enabled_services": sorted(name for name, service in model.services.items() if service.enabled),
        "model_digest": model_digest(model),
    }


__all__ = [
    "CanonicalSite",
    "CanonicalValuesError",
    "load_site",
    "model_digest",
    "normalized_model",
    "redacted_summary",
]
