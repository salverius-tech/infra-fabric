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
        if value is None:
            return None
        if isinstance(value, Mapping):
            if part not in value:
                raise ProjectionError(f"canonical projection path does not exist: {path}")
            value = value[part]
        elif isinstance(value, list) and part.isdecimal():
            index = int(part)
            if index >= len(value):
                raise ProjectionError(f"canonical projection path does not exist: {path}")
            value = value[index]
        else:
            if not hasattr(value, part):
                raise ProjectionError(f"canonical projection path does not exist: {path}")
            value = getattr(value, part)
    return value


def _compatibility_value(
    model_or_service: CanonicalSite | Any,
    service_or_resource: Any,
    resource_or_path: Any,
    path: str | None = None,
) -> Any:
    if path is None:
        model = None
        service = model_or_service
        resource = service_or_resource
        path = resource_or_path
    else:
        model = model_or_service
        service = service_or_resource
        resource = resource_or_path
    assert isinstance(path, str)
    if path.startswith("resources."):
        if model is not None:
            try:
                return _path_value(model, path)
            except ProjectionError:
                parts = path.split(".")
                if len(parts) >= 4 and parts[1] in {"guests", "shared_hosts"}:
                    return _path_value(resource, ".".join(parts[3:]))
                raise
        parts = path.split(".")
        if len(parts) >= 4 and parts[1] in {"guests", "shared_hosts"}:
            return _path_value(resource, ".".join(parts[3:]))
        raise ProjectionError(f"canonical projection path requires a model: {path}")
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


def _bootstrap_ssh_keys(model: CanonicalSite, resource_id: str) -> list[str]:
    policy = model.bootstrap.ssh
    keys = list(policy.public_keys)
    for key in policy.host_additional_keys.get(resource_id, []):
        if key not in keys:
            keys.append(key)
    return keys


def _operator_ssh_keys(model: CanonicalSite, resource_id: str) -> list[str]:
    policy = model.operator.ssh
    keys = list(policy.public_keys)
    for key in policy.host_additional_keys.get(resource_id, []):
        if key not in keys:
            keys.append(key)
    return keys


def _bootstrap_ssh_user(model: CanonicalSite, resource: Any) -> str:
    return resource.runtime.cloud_init_user or model.bootstrap.ssh.user


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
        "bootstrap_ssh_user": model.bootstrap.ssh.user,
        "bootstrap_ssh_public_keys": {
            resource_id: _bootstrap_ssh_keys(model, resource_id)
            for resource_id in (*model.resources.guests, *model.resources.shared_hosts)
        },
        "operator_user": model.operator.user,
        "operator_ssh_public_keys": {
            resource_id: _operator_ssh_keys(model, resource_id)
            for resource_id in (*model.resources.guests, *model.resources.shared_hosts)
        },
        "operator_dotfiles_repository": model.operator.dotfiles.repository,
        "operator_dotfiles_revision": model.operator.dotfiles.revision,
        "operator_chezmoi_version": model.operator.dotfiles.chezmoi.version,
        "operator_chezmoi_sha256": model.operator.dotfiles.chezmoi.sha256,
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
        if name == "forgejo" and isinstance(service.configuration.get("database"), dict):
            values["forgejo_database"] = dict(service.configuration["database"])
        if service.resource:
            resource = _resource(model, service.resource)
            if resource.storage.volumes:
                values.setdefault("service_storage", {})[name] = {
                    volume_name: volume.model_dump(mode="python")
                    for volume_name, volume in resource.storage.volumes.items()
                }
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
    management = model.platform.proxmox.management
    if management is not None:
        hosts["pve"] = {
            "canonical_site": model.site.name,
            "canonical_platform": "proxmox",
            "ansible_host": management.host,
            "ansible_user": management.user,
        }
        groups["proxmox"] = {"hosts": ["pve"]}
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
            "ansible_user": _bootstrap_ssh_user(model, resource),
            "bootstrap_ssh_public_keys": _bootstrap_ssh_keys(model, service.resource or ""),
            "operator_user": model.operator.user,
            "operator_ssh_public_keys": _operator_ssh_keys(model, service.resource or ""),
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
        legacy_vars: dict[str, Any] = {}
        compatibility = capability.inventory.get("canonical_play_vars")
        if isinstance(compatibility, Mapping):
            legacy_vars: dict[str, Any] = {}
            for legacy_name, canonical_path in compatibility.items():
                if not isinstance(legacy_name, str) or not isinstance(canonical_path, str):
                    raise ProjectionError(f"invalid canonical compatibility mapping for service {name}")
                if name == "forgejo" and legacy_name == "forgejo_ssh_port" and "ssh" not in service.endpoints.protocols:
                    continue
                value = _compatibility_value(model, service, resource, canonical_path)
                if value is not None:
                    legacy_vars[legacy_name] = value
        if name == "technitium":
            caddy = service.configuration.get("caddy")
            if isinstance(caddy, Mapping) and caddy.get("enabled", True):
                upstream = caddy["upstream"]
                legacy_vars.update(
                    {
                        "caddy_email": model.platform.ingress.acme.email,
                        "caddy_server_name": caddy["server_names"][0],
                        "caddy_server_names": list(caddy["server_names"]),
                        "caddy_upstream": f"{upstream['host']}:{upstream['port']}",
                        "caddy_extra_vhosts": list(caddy.get("extra_vhosts", [])),
                    }
                )
        if name == "onramp_host":
            legacy_vars["onramp_host_bootstrap_ssh_public_keys"] = _bootstrap_ssh_keys(model, service.resource or "")
        if legacy_vars:
            service_vars["legacy_vars"] = legacy_vars
        services[name] = service_vars
    result = {"canonical_site": model.site.name, "services": services}
    _assert_non_secret(result, "ansible")
    return result


def render_dns_records(model: CanonicalSite) -> dict[str, Any]:
    """Render canonical DNS ownership plus derived service endpoint records."""
    dns = model.platform.dns
    records = dict(dns.a_records)
    cname_records = dict(dns.cname_records)
    for name, service in model.services.items():
        if not service.enabled or not service.endpoints.dns.enabled:
            continue
        address = _address(_resource(model, service.resource or ""))
        if not address:
            raise ProjectionError(f"DNS-enabled service {name} has no verified resource address")
        try:
            address = str(ipaddress.IPv4Address(address))
        except ValueError as error:
            raise ProjectionError(f"DNS-enabled service {name} has invalid resource address") from error
        for public_name in service.endpoints.public_names:
            if public_name in cname_records:
                raise ProjectionError(f"DNS record conflicts with canonical CNAME: {public_name}")
            if public_name in records and records[public_name] != address:
                raise ProjectionError(f"DNS record target conflicts for {public_name}")
            records[public_name] = address
    settings: dict[str, Any] = {}
    if dns.settings is not None:
        settings = {
            "forwarders": list(dns.settings.forwarders),
            "forwarderProtocol": dns.settings.forwarder_protocol,
            "concurrentForwarding": dns.settings.concurrent_forwarding,
            "dnssecValidation": dns.settings.dnssec_validation,
            "preferIPv6": dns.settings.prefer_ipv6,
        }
    return {
        "a_records": dict(sorted(records.items())),
        "cname_records": dict(sorted(cname_records.items())),
        "zones": {zone: list(forwarders) for zone, forwarders in sorted(dns.zones.items())},
        "settings": settings,
    }


def verify_cross_projection_identity(
    *,
    site: str,
    opentofu: Mapping[str, Any],
    inventory: Mapping[str, Any],
    ansible_vars: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify service/resource/runtime identity across generated projections."""
    inventory_site = inventory.get("all", {}).get("vars", {}).get("canonical_site")
    vars_site = ansible_vars.get("canonical_site")
    if inventory_site != site or vars_site != site:
        raise ProjectionError("generated projections disagree with the selected site")
    hosts = inventory.get("_meta", {}).get("hostvars", {})
    services = ansible_vars.get("services")
    runtimes = opentofu.get("service_runtime")
    if not isinstance(hosts, Mapping) or not isinstance(services, Mapping) or not isinstance(runtimes, Mapping):
        raise ProjectionError("generated projections have an invalid identity shape")
    if set(services) != set(runtimes):
        raise ProjectionError("service identity sets disagree across projections")
    identities: dict[str, dict[str, str]] = {}
    for name, values in services.items():
        if not isinstance(values, Mapping):
            raise ProjectionError(f"Ansible vars identity is invalid: {name}")
        resource = values.get("resource")
        resource_type = values.get("resource_type")
        runtime = runtimes.get(name)
        if not isinstance(resource, str) or not isinstance(resource_type, str) or not isinstance(runtime, Mapping):
            raise ProjectionError(f"projection identity is incomplete: {name}")
        if runtime.get("type") != resource_type:
            raise ProjectionError(f"runtime type disagrees across projections: {name}")
        matching_hosts = [
            hostvars
            for hostvars in hosts.values()
            if isinstance(hostvars, Mapping) and hostvars.get("canonical_service") == name
        ]
        if len(matching_hosts) != 1 or matching_hosts[0].get("canonical_resource") != resource:
            raise ProjectionError(f"resource identity disagrees across projections: {name}")
        identities[name] = {"resource": resource, "resource_type": resource_type}
    return {"site": site, "services": identities, "status": "verified"}


__all__ = [
    "ProjectionError",
    "render_ansible_inventory",
    "render_ansible_vars",
    "render_dns_records",
    "render_opentofu_variables",
    "verify_cross_projection_identity",
]
