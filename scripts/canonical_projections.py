#!/usr/bin/env python3
"""Render non-secret consumer projections from a canonical site model."""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Mapping

from canonical_values import CanonicalSite
from service_catalog import ServiceCatalog


class ProjectionError(ValueError):
    """Raised when a canonical model cannot produce a safe projection."""


_SENSITIVE_KEY = re.compile(r"(?:password|passphrase|secret|token|private[_-]?key|api[_-]?key|credential)", re.IGNORECASE)


def _assert_non_secret(value: Any, path: str = "projection") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and _SENSITIVE_KEY.search(key):
                raise ProjectionError(f"non-secret projection contains sensitive field: {path}.{key}")
            _assert_non_secret(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_non_secret(child, f"{path}[{index}]")


def _validate_non_secret_inputs(model: CanonicalSite) -> None:
    for name, resource in (*model.resources.guests.items(), *model.resources.shared_hosts.items()):
        for field_name, value in (("runtime.cloud_init", resource.runtime.cloud_init), ("runtime.template", resource.runtime.template), ("runtime.users", resource.runtime.users)):
            if value:
                raise ProjectionError(f"non-secret projection rejects opaque field: resources.{name}.{field_name}")
    for name, service in model.services.items():
        for field_name, value in (("configuration", service.configuration), ("overrides", service.overrides)):
            if value:
                _assert_non_secret(value, f"services.{name}.{field_name}")


def _address(resource: Any) -> str:
    value = resource.network.address
    if value == "dhcp":
        value = resource.network.expected_address or ""
    return value.split("/", 1)[0]


def _resource(model: CanonicalSite, name: str) -> Any:
    resource = model.resources.guests.get(name) or model.resources.shared_hosts.get(name)
    if resource is None:
        raise ProjectionError(f"resource does not exist: {name}")
    return resource


def _path_value(value: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(value, Mapping):
            if part not in value:
                raise ProjectionError(f"canonical projection path does not exist: {path}")
            value = value[part]
        else:
            if not hasattr(value, part):
                raise ProjectionError(f"canonical projection path does not exist: {path}")
            value = getattr(value, part)
    return value


def _compatibility_value(service: Any, resource: Any, path: str) -> Any:
    if path.startswith("resource."):
        return _path_value(resource, path.removeprefix("resource."))
    return _path_value(service, path)


def _resource_variables(name: str, resource: Any) -> dict[str, Any]:
    prefix = name if resource.type == "vm" else f"{name}_container"
    network = resource.network
    values: dict[str, Any] = {
        f"{prefix}_vmid": resource.identity.vmid,
        f"{prefix}_hostname": resource.identity.hostname,
        f"{prefix}_description": resource.identity.description or "",
        f"{prefix}_ipv4_address": network.address,
        f"{prefix}_cores": resource.compute.cores,
        f"{prefix}_memory_mb": resource.compute.memory_mb,
        f"{prefix}_swap_mb": resource.compute.swap_mb,
        f"{prefix}_disk_gb": resource.storage.root.size_gb,
    }
    if name == "onramp_host":
        values["onramp_host_datastore_id"] = resource.storage.root.storage_id
        if resource.runtime.cloud_init_user is not None:
            values["onramp_host_cloud_init_user"] = resource.runtime.cloud_init_user
    if name in {"forgejo_runner", "infisical", "hermes", "tailscale_client", "onramp_host"}:
        values[f"{name}_started"] = resource.runtime.started
        values[f"{name}_start_on_boot"] = resource.runtime.start_on_boot
    if network.gateway is not None:
        values[f"{prefix}_ipv4_gateway"] = network.gateway
    if network.dns_servers:
        values[f"{prefix}_dns_servers"] = list(network.dns_servers)
    if network.search_domain is not None:
        values[f"{prefix}_search_domain"] = network.search_domain
    if network.mac_address is not None:
        values[f"{prefix}_mac_address"] = network.mac_address
    if network.bridge is not None:
        values[f"{prefix}_bridge"] = network.bridge
    if network.vlan_id is not None:
        values[f"{prefix}_vlan_id"] = network.vlan_id
    return values


def render_opentofu_variables(model: CanonicalSite) -> dict[str, Any]:
    """Render existing OpenTofu variable names without secret material."""
    _validate_non_secret_inputs(model)
    values: dict[str, Any] = {
        "enabled_services": sorted(name for name, service in model.services.items() if service.enabled),
        "proxmox_endpoint": model.platform.proxmox.endpoint,
        "proxmox_node_name": model.platform.proxmox.node,
        "proxmox_insecure": model.platform.proxmox.insecure,
        "rootfs_datastore_id": model.platform.storage.rootfs_datastore,
        "template_datastore_id": model.platform.storage.template_datastore,
    }
    if model.platform.vm_cloud_init_user is not None:
        values["guest_vm_cloud_init_user"] = model.platform.vm_cloud_init_user
    if model.platform.lxc_template_download_timeout_seconds is not None:
        values["lxc_template_download_timeout_seconds"] = model.platform.lxc_template_download_timeout_seconds
    for name, resource in (*model.resources.guests.items(), *model.resources.shared_hosts.items()):
        values.update(_resource_variables(name, resource))
    runtimes: dict[str, dict[str, Any]] = {}
    for name, service in model.services.items():
        if service.enabled:
            resource = _resource(model, service.resource or "")
            runtimes[name] = {"type": resource.type}
            if resource.runtime.cloud_init_user is not None:
                runtimes[name]["cloud_init_user"] = resource.runtime.cloud_init_user
            if resource.type == "vm" and resource.runtime.cloud_init:
                runtimes[name].update(resource.runtime.cloud_init)
    values["service_runtime"] = runtimes
    image_names = (
        ("lxc", "debian", "debian_template"),
        ("vm", "guest", "guest_vm_image"),
        ("vm", "onramp_host", "onramp_host_image"),
    )
    for family, name, prefix in image_names:
        image = model.platform.images.model_dump(mode="python").get(family, {}).get(name)
        if not image:
            continue
        if family == "vm":
            values[f"{prefix}_datastore_id"] = image["datastore_id"]
        values[f"{prefix}_url"] = image["url"]
        values[f"{prefix}_file_name"] = image["file_name"]
        values[f"{prefix}_checksum_algorithm"] = image["checksum"]["algorithm"]
        values[f"{prefix}_checksum"] = image["checksum"]["value"]
    for name, service in model.services.items():
        if not service.enabled:
            continue
        endpoint_names = service.endpoints.public_names
        if endpoint_names:
            values[f"{name}_server_name"] = endpoint_names[0]
        if service.endpoints.public_url:
            values[f"{name}_public_url"] = service.endpoints.public_url
    _assert_non_secret(values, "opentofu")
    return values


def render_ansible_inventory(model: CanonicalSite, catalog: ServiceCatalog) -> dict[str, Any]:
    """Render a minimal dynamic-inventory contract from resources and services."""
    hosts: dict[str, dict[str, Any]] = {}
    groups: dict[str, dict[str, Any]] = {}
    for name, service in model.services.items():
        if not service.enabled:
            continue
        capability = catalog.get(name)
        resource = _resource(model, service.resource or "")
        host = str(capability.inventory.get("host", service.resource))
        group = str(capability.inventory.get("group", name))
        hostvars = {
            "canonical_site": model.site.name,
            "canonical_resource": service.resource,
            "canonical_service": name,
            "ansible_host": _address(resource),
            "service_runtime_current": {"type": resource.type},
        }
        hosts[host] = {**hosts.get(host, {}), **hostvars}
        groups.setdefault(group, {"hosts": []})["hosts"].append(host)
    for group in groups.values():
        group["hosts"] = sorted(set(group["hosts"]))
    result = {
        "_meta": {"hostvars": hosts},
        "all": {"children": sorted(groups), "vars": {"canonical_site": model.site.name}},
        **groups,
    }
    _assert_non_secret(result, "inventory")
    return result


def render_ansible_vars(model: CanonicalSite, catalog: ServiceCatalog) -> dict[str, Any]:
    """Render non-secret service variables from canonical ownership.

    The result deliberately keeps service configuration namespaced by service.
    Consumer-specific flattening belongs in the Ansible adapter, not in the
    canonical model or operator-edited YAML.
    """
    _validate_non_secret_inputs(model)
    services: dict[str, Any] = {}
    for name, service in sorted(model.services.items()):
        if not service.enabled:
            continue
        capability = catalog.get(name)
        resource = _resource(model, service.resource or "")
        service_vars = {
            "resource": service.resource,
            "resource_type": resource.type,
            "runtime": resource.runtime.model_dump(mode="json", exclude_none=True),
            "security": resource.security.model_dump(mode="json", exclude={"ssh_public_keys"}, exclude_none=True),
            "endpoints": service.endpoints.model_dump(mode="json", exclude_none=True),
            "release": service.release.model_dump(mode="json", exclude_none=True),
            "configuration": service.configuration,
            "overrides": service.overrides,
            "catalog": {
                "inventory_host": capability.inventory.get("host"),
                "inventory_group": capability.inventory.get("group"),
            },
        }
        compatibility = capability.inventory.get("canonical_play_vars")
        if isinstance(compatibility, Mapping):
            legacy_vars: dict[str, Any] = {}
            for legacy_name, canonical_path in compatibility.items():
                if not isinstance(legacy_name, str) or not isinstance(canonical_path, str):
                    raise ProjectionError(f"invalid canonical compatibility mapping for service {name}")
                value = _compatibility_value(service, resource, canonical_path)
                if value is not None:
                    legacy_vars[legacy_name] = value
            if legacy_vars:
                service_vars["legacy_vars"] = legacy_vars
        services[name] = service_vars
    result = {"canonical_site": model.site.name, "services": services}
    _assert_non_secret(result, "ansible")
    return result


def render_dns_records(model: CanonicalSite) -> dict[str, Any]:
    """Render the existing DNS projection shape from endpoint intent."""
    records: dict[str, str] = {}
    for name, service in model.services.items():
        if not service.enabled or not service.endpoints.dns.enabled:
            continue
        address = _address(_resource(model, service.resource or ""))
        if not address:
            raise ProjectionError(f"DNS-enabled service {name} has no verified resource address")
        try:
            ipaddress.ip_address(address)
        except ValueError as error:
            raise ProjectionError(f"DNS-enabled service {name} has invalid resource address") from error
        for public_name in service.endpoints.public_names:
            records[public_name] = address
    return {"a_records": dict(sorted(records.items())), "cname_records": {}, "zones": {}, "settings": {}}


__all__ = [
    "ProjectionError",
    "render_ansible_inventory",
    "render_ansible_vars",
    "render_dns_records",
    "render_opentofu_variables",
]
