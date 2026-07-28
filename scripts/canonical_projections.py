#!/usr/bin/env python3
"""Render non-secret consumer projections from a canonical site model."""
from __future__ import annotations

import ipaddress
import re
from typing import Any

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
    if network.gateway is not None:
        values[f"{prefix}_ipv4_gateway"] = network.gateway
    if network.dns_servers:
        values[f"{prefix}_dns_servers"] = list(network.dns_servers)
    if network.search_domain is not None:
        values[f"{prefix}_search_domain"] = network.search_domain
    if network.bridge is not None:
        values[f"{prefix}_bridge"] = network.bridge
    if network.vlan_id is not None:
        values[f"{prefix}_vlan_id"] = network.vlan_id
    return values


def render_opentofu_variables(model: CanonicalSite) -> dict[str, Any]:
    """Render existing OpenTofu variable names without secret material."""
    values: dict[str, Any] = {
        "enabled_services": sorted(name for name, service in model.services.items() if service.enabled),
        "proxmox_endpoint": model.platform.proxmox.endpoint,
        "proxmox_node_name": model.platform.proxmox.node,
        "proxmox_insecure": model.platform.proxmox.insecure,
        "rootfs_datastore_id": model.platform.storage.rootfs_datastore,
        "template_datastore_id": model.platform.storage.template_datastore,
    }
    for name, resource in (*model.resources.guests.items(), *model.resources.shared_hosts.items()):
        values.update(_resource_variables(name, resource))
    runtimes: dict[str, dict[str, Any]] = {}
    for name, service in model.services.items():
        if service.enabled:
            resource = _resource(model, service.resource or "")
            runtimes[name] = {"type": resource.type}
            if resource.type == "vm" and resource.runtime.cloud_init:
                runtimes[name].update(resource.runtime.cloud_init)
    values["service_runtime"] = runtimes
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
    services: dict[str, Any] = {}
    for name, service in sorted(model.services.items()):
        if not service.enabled:
            continue
        capability = catalog.get(name)
        resource = _resource(model, service.resource or "")
        services[name] = {
            "resource": service.resource,
            "resource_type": resource.type,
            "runtime": resource.runtime.model_dump(mode="json", exclude_none=True),
            "endpoints": service.endpoints.model_dump(mode="json", exclude_none=True),
            "release": service.release.model_dump(mode="json", exclude_none=True),
            "configuration": service.configuration,
            "overrides": service.overrides,
            "catalog": {
                "inventory_host": capability.inventory.get("host"),
                "inventory_group": capability.inventory.get("group"),
            },
        }
    result = {"canonical_site": model.site.name, "services": services}
    _assert_non_secret(result, "ansible")
    return result


def render_dns_records(model: CanonicalSite) -> dict[str, Any]:
    """Render the existing DNS projection shape from endpoint intent."""
    records: dict[str, str] = {}
    for name, service in model.services.items():
        if not service.enabled or not service.endpoints.dns.get("enabled", False):
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
