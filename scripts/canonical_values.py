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
from typing import Any, Literal

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
_CIDR_RE = re.compile(r"^(?:dhcp|(?:[0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2})$")
_CHECKSUM_RE = re.compile(r"^[0-9a-fA-F]{64}|[0-9a-fA-F]{128}$")


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
    url: StrictStr
    file_name: StrictStr
    checksum: ImageChecksum


class PlatformImages(StrictModel):
    lxc: dict[str, ImageDefinition] = Field(default_factory=dict)
    vm: dict[str, ImageDefinition] = Field(default_factory=dict)


class Platform(StrictModel):
    proxmox: ProxmoxPlatform
    network: NetworkDefaults
    storage: StorageDefaults
    images: PlatformImages = Field(default_factory=PlatformImages)


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
    unprivileged: StrictBool | None = None
    nesting: StrictBool | None = None
    features: dict[str, StrictBool] = Field(default_factory=dict)
    template: dict[str, StrictStr] | None = None
    firmware: Literal["uefi", "seabios"] | None = None
    machine: StrictStr | None = None
    guest_agent: StrictBool | None = None
    cloud_init: dict[str, Any] | None = None
    users: dict[str, dict[str, Any]] = Field(default_factory=dict)


class Resource(StrictModel):
    type: Literal["lxc", "vm"]
    identity: ResourceIdentity
    network: ResourceNetwork
    compute: ResourceCompute
    storage: ResourceStorage
    runtime: ResourceRuntime

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


class ServiceState(StrictModel):
    capable: StrictBool = False
    backup: dict[str, Any] = Field(default_factory=dict)
    disable_policy: Literal["retain", "archive", "destroy"] | None = None


class ServiceEndpoints(StrictModel):
    public_names: list[StrictStr] = Field(default_factory=list)
    public_url: StrictStr | None = None
    protocols: list[StrictStr] = Field(default_factory=list)
    ports: dict[str, StrictInt] = Field(default_factory=dict)
    visibility: Literal["internal", "public", "none"] = "internal"
    dns: dict[str, Any] = Field(default_factory=dict)

    @field_validator("public_names")
    @classmethod
    def validate_names(cls, value: list[str]) -> list[str]:
        normalized = [name.lower().rstrip(".") for name in value]
        if any(not _HOSTNAME_RE.fullmatch(name) for name in normalized):
            raise ValueError("service endpoint public_names must contain valid hostnames")
        if len(normalized) != len(set(normalized)):
            raise ValueError("service endpoint public_names must be unique")
        return normalized


class ServiceRelease(StrictModel):
    version: StrictStr | None = None
    image: StrictStr | None = None
    digest: StrictStr | None = None
    checksum: StrictStr | None = None
    source: Literal["package", "container", "binary", "image"] | None = None

    @model_validator(mode="after")
    def validate_release(self) -> "ServiceRelease":
        if self.source == "container" and (not self.image or not self.digest):
            raise ValueError("container releases require image and immutable digest")
        if self.source in {"package", "binary"} and not self.version:
            raise ValueError(f"{self.source} releases require version")
        if self.source == "package" and self.digest:
            raise ValueError("package releases cannot declare digest")
        return self


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
            catalog.validate_model_services(model.services)
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
