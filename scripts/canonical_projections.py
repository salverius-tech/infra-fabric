#!/usr/bin/env python3
"""Render non-secret consumer projections from a canonical site model."""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Any, Mapping

from canonical_values import CanonicalSite, model_digest
from service_catalog import ServiceCatalog, load_catalog


class ProjectionError(ValueError):
    """Raised when a canonical model cannot produce a safe projection."""


_SENSITIVE_KEY = re.compile(r"(?:password|passphrase|secret|token|private[_-]?key|api[_-]?key|credential)", re.IGNORECASE)
_ENVIRONMENT_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
ONRAMP_HANDOFF_API_VERSION = "infra-fabric.onramp-handoff/v1"


def _is_sensitive_key(key: str, value: Any) -> bool:
    if isinstance(value, bool) and (key.endswith("passwordless_sudo") or key.endswith("password_authentication")):
        return False
    return bool(_SENSITIVE_KEY.search(key))


def _assert_non_secret(value: Any, path: str = "projection") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and _is_sensitive_key(key, child):
                raise ProjectionError(f"non-secret projection contains sensitive field: {path}.{key}")
            _assert_non_secret(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_non_secret(child, f"{path}[{index}]")


def render_runtime_env(
    values: Mapping[str, str],
    *,
    allowed_keys: set[str],
    secret_keys: set[str] | None = None,
) -> str:
    """Render an allow-listed dotenv payload for transient runtime delivery.

    This helper intentionally does not write a file. Callers must keep the
    returned payload in the protected temporary-material boundary, especially
    when ``secret_keys`` are present. Canonical projections never infer process
    environment names from logical secret paths; the caller supplies the
    explicit, catalog-owned names.
    """
    if not isinstance(values, Mapping) or not isinstance(allowed_keys, set):
        raise ProjectionError("runtime environment inputs must be mappings and an allow-list set")
    secret_keys = secret_keys or set()
    if not secret_keys <= allowed_keys:
        raise ProjectionError("runtime secret keys must be explicitly allow-listed")
    if set(values) - allowed_keys:
        raise ProjectionError("runtime environment contains an undeclared key")
    if not secret_keys <= set(values):
        raise ProjectionError("runtime environment is missing a declared secret key")
    lines: list[str] = []
    for key in sorted(values):
        if not isinstance(key, str) or not _ENVIRONMENT_KEY.fullmatch(key):
            raise ProjectionError("runtime environment contains an invalid key")
        value = values[key]
        if not isinstance(value, str) or "\n" in value or "\r" in value:
            raise ProjectionError(f"runtime environment value is invalid: {key}")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
        lines.append(f'{key}="{escaped}"')
    return "\n".join(lines) + ("\n" if lines else "")


def _validate_non_secret_inputs(model: CanonicalSite) -> None:
    for name, resource in (*model.resources.guests.items(), *model.resources.shared_hosts.items()):
        for field_name, value in (("runtime.cloud_init", resource.runtime.cloud_init), ("runtime.template", resource.runtime.template), ("runtime.users", resource.runtime.users)):
            if value:
                raise ProjectionError(f"non-secret projection rejects opaque field: resources.{name}.{field_name}")
    for name, service in model.services.items():
        if service.configuration:
            _assert_non_secret(service.configuration, f"services.{name}.configuration")


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


def _resolve_mapping_value(
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
    # Forgejo Runner is an LXC resource whose existing OpenTofu interface uses
    # the unsuffixed forgejo_runner_* variable names. Keep this compatibility
    # exception explicit until the consumer naming audit is complete.
    prefix = name if resource.type == "vm" or name in {"forgejo_runner", "tailscale_client"} else f"{name}_container"
    network = resource.network
    values: dict[str, Any] = {
        f"{prefix}_vmid": resource.identity.vmid,
        f"{prefix}_hostname": resource.identity.hostname,
        f"{prefix}_description": resource.identity.description or "",
        f"{prefix}_ipv4_address": network.address,
        f"{prefix}_cores": resource.compute.cores,
        f"{prefix}_memory_mb": resource.compute.memory_mb,
        f"{prefix}_disk_gb": resource.storage.root.size_gb,
    }
    if name == "sssf":
        data_volume = resource.storage.volumes.get("data")
        if data_volume is None or data_volume.size_gb is None:
            raise ProjectionError("sssf resource must declare a sized storage.volumes.data volume")
        values["sssf_data_disk_gb"] = data_volume.size_gb
    if resource.type == "lxc":
        values[f"{prefix}_swap_mb"] = resource.compute.swap_mb
    if name == "onramp_host":
        values["onramp_host_datastore_id"] = resource.storage.root.storage_id
    if name in {"forgejo_runner", "infisical", "hermes", "sssf", "tailscale_client", "onramp_host"}:
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
    del resource
    return model.bootstrap.ssh.user


def render_opentofu_variables(model: CanonicalSite, catalog: ServiceCatalog | None = None) -> dict[str, Any]:
    """Render existing OpenTofu variable names without secret material."""
    _validate_non_secret_inputs(model)
    catalog = catalog or load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
    values: dict[str, Any] = {
        "enabled_services": sorted(name for name, service in model.services.items() if service.enabled),
        "stateful_service_disable_policies": {
            name: service.state.disable_policy
            for name, service in sorted(model.services.items())
            if service.state.capable
        },
        "vm_cpu_types": {
            resource_id: resource.compute.cpu_type
            for resource_id, resource in sorted((*model.resources.guests.items(), *model.resources.shared_hosts.items()))
            if resource.type == "vm"
        },
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
    if model.platform.lxc_template_download_timeout_seconds is not None:
        values["lxc_template_download_timeout_seconds"] = model.platform.lxc_template_download_timeout_seconds
    enabled_resources = {
        service.resource
        for service in model.services.values()
        if service.enabled and service.resource is not None
    }
    for name, resource in (*model.resources.guests.items(), *model.resources.shared_hosts.items()):
        if name in enabled_resources:
            values.update(_resource_variables(name, resource))
    forgejo = model.resources.guests.get("forgejo")
    if forgejo is not None:
        values["forgejo_lan_ip"] = _address(forgejo)
    runtimes: dict[str, dict[str, Any]] = {}
    for name, service in model.services.items():
        if service.enabled and catalog.get(name).runtime_owner in {"guest", "shared_host"}:
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
        resource = _resource(model, service.resource or "")
        inventory = catalog.get(name).inventory
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
        tf_domain = catalog.get(name).inventory.get("tf_domain")
        if endpoint_names and isinstance(tf_domain, str) and tf_domain not in values:
            values[tf_domain] = endpoint_names[0]
        opentofu_ansible_var_mappings = catalog.get(name).inventory.get("opentofu_ansible_var_mappings")
        if isinstance(opentofu_ansible_var_mappings, Mapping):
            ansible_var_mappings = inventory.get("ansible_var_mappings")
            for tf_key in opentofu_ansible_var_mappings.values():
                if not isinstance(tf_key, str) or tf_key in values:
                    continue
                if tf_key.endswith("_server_name") and endpoint_names:
                    values[tf_key] = endpoint_names[0]
                elif tf_key.endswith("_public_url") and not tf_key.endswith("_enable_public_url") and service.endpoints.public_url:
                    values[tf_key] = service.endpoints.public_url
                elif isinstance(ansible_var_mappings, Mapping) and isinstance(ansible_var_mappings.get(tf_key), str):
                    try:
                        value = _resolve_mapping_value(model, service, resource, ansible_var_mappings[tf_key])
                    except ProjectionError:
                        continue
                    if value is not None:
                        values[tf_key] = value
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
        groups["proxmox"] = {"hosts": {"pve": {}}}
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
            "bootstrap_ssh_user": model.bootstrap.ssh.user,
            "bootstrap_ssh_public_keys": _bootstrap_ssh_keys(model, service.resource or ""),
            "operator_user": model.operator.user,
            "operator_ssh_public_keys": _operator_ssh_keys(model, service.resource or ""),
            "service_runtime_current": {"type": resource.type},
        }
        if host in hosts:
            existing = hosts[host]
            services_for_host = existing.setdefault("canonical_services", [existing["canonical_service"]])
            services_for_host.append(name)
        else:
            hosts[host] = {**hostvars, "canonical_services": [name]}
        groups.setdefault(group, {"hosts": {}})["hosts"][host] = {}
    for group in groups.values():
        for host in group["hosts"]:
            group["hosts"][host] = hosts[host]
    result = {
        "all": {
            "children": {group: {} for group in sorted(groups)},
            "vars": {
                "canonical_site": model.site.name,
                "ansible_ssh_common_args": (
                    "-o UserKnownHostsFile=/workspace/values/sites/"
                    f"{model.site.name}/ansible/known_hosts -o StrictHostKeyChecking=yes"
                ),
            },
        },
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
    opentofu_values = render_opentofu_variables(model, catalog)
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
            "catalog": {
                "inventory_host": capability.inventory.get("host"),
                "inventory_group": capability.inventory.get("group"),
            },
        }
        ansible_vars: dict[str, Any] = {}
        ansible_var_mappings = capability.inventory.get("ansible_var_mappings")
        if isinstance(ansible_var_mappings, Mapping):
            ansible_vars: dict[str, Any] = {}
            for ansible_var_name, canonical_path in ansible_var_mappings.items():
                if not isinstance(ansible_var_name, str) or not isinstance(canonical_path, str):
                    raise ProjectionError(f"invalid canonical Ansible variable mapping for service {name}")
                if name == "forgejo" and ansible_var_name == "forgejo_ssh_port" and "ssh" not in service.endpoints.protocols:
                    continue
                value = _resolve_mapping_value(model, service, resource, canonical_path)
                if value is not None:
                    ansible_vars[ansible_var_name] = value
        opentofu_ansible_var_mappings = capability.inventory.get("opentofu_ansible_var_mappings")
        if isinstance(opentofu_ansible_var_mappings, Mapping):
            for ansible_var_name, tf_key in opentofu_ansible_var_mappings.items():
                if isinstance(ansible_var_name, str) and isinstance(tf_key, str) and tf_key in opentofu_values:
                    ansible_vars[ansible_var_name] = opentofu_values[tf_key]
        ansible_vmid_var = capability.inventory.get("ansible_vmid_var")
        if isinstance(ansible_vmid_var, str) and ansible_vmid_var:
            ansible_vars[ansible_vmid_var] = resource.identity.vmid
        ansible_vars[f"{name}_runtime"] = resource.runtime.model_dump(mode="json", exclude_none=True)
        ansible_vars["caddy_email"] = model.platform.ingress.acme.email
        if name == "technitium":
            caddy = service.configuration.get("caddy")
            if isinstance(caddy, Mapping) and caddy.get("enabled", True):
                upstream = caddy["upstream"]
                ansible_vars.update(
                    {
                        "caddy_email": model.platform.ingress.acme.email,
                        "caddy_server_name": caddy["server_names"][0],
                        "caddy_server_names": list(caddy["server_names"]),
                        "caddy_upstream": f"{upstream['host']}:{upstream['port']}",
                        "caddy_extra_vhosts": list(caddy.get("extra_vhosts", [])),
                    }
                )
        if name == "onramp_host":
            ansible_vars["onramp_host_bootstrap_ssh_public_keys"] = _bootstrap_ssh_keys(model, service.resource or "")
        if ansible_vars:
            service_vars["ansible_vars"] = ansible_vars
        services[name] = service_vars
    result = {
        "canonical_site": model.site.name,
        "bootstrap_ssh_user": model.bootstrap.ssh.user,
        "operator_user": model.operator.user,
        "operator_dotfiles_repository": model.operator.dotfiles.repository,
        "operator_dotfiles_revision": model.operator.dotfiles.revision,
        "operator_chezmoi_version": model.operator.dotfiles.chezmoi.version,
        "operator_chezmoi_sha256": model.operator.dotfiles.chezmoi.sha256,
        "services": services,
    }
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


def render_onramp_handoff(model: CanonicalSite, catalog: ServiceCatalog) -> dict[str, Any]:
    """Render the versioned, non-secret shared-host contract for Onramp.

    The projection describes substrate identity and ownership boundaries only.
    It deliberately grants no Proxmox lifecycle authority and contains no SSH
    keys, provider inputs, generated-file write authority, protected values, VMID,
    datastore, image-acquisition metadata, or application definitions.
    """
    service = model.services.get("onramp_host")
    capability = catalog.get("onramp_host")
    handoff = capability.handoff
    if capability.runtime_owner != "shared_host" or capability.runtime is None:
        raise ProjectionError("onramp_host catalog ownership must remain VM shared_host")
    if handoff is None or handoff.get("api_version") != ONRAMP_HANDOFF_API_VERSION:
        raise ProjectionError("onramp_host catalog handoff metadata is unavailable")
    enabled = bool(service and service.enabled)
    resource_id = service.resource if enabled and service is not None else None
    result: dict[str, Any] = {
        "api_version": ONRAMP_HANDOFF_API_VERSION,
        "kind": "OnrampSubstrate",
        "metadata": {
            "canonical_site": model.site.name,
            "canonical_model_digest": model_digest(model),
            "canonical_service": "onramp_host",
            "canonical_resource": resource_id,
            "enabled": enabled,
        },
        "spec": None,
    }
    if not enabled:
        _assert_non_secret(result, "onramp_handoff")
        return result
    assert service is not None
    if not service.resource:
        raise ProjectionError("enabled onramp_host service has no canonical resource")
    resource = model.resources.shared_hosts.get(service.resource)
    if resource is None:
        raise ProjectionError("onramp handoff resource must be owned by resources.shared_hosts")
    if resource.type != "vm" or resource.type not in capability.runtime.supported_types:
        raise ProjectionError("onramp handoff requires a catalog-supported VM shared host")
    address = _address(resource)
    if not address:
        raise ProjectionError("onramp handoff requires a deterministic resource address")
    try:
        address = str(ipaddress.IPv4Address(address))
    except ValueError as error:
        raise ProjectionError("onramp handoff requires a valid deterministic IPv4 address") from error
    deploy_user = resource.security.deploy_user
    deploy_dir = resource.security.deploy_dir
    if not deploy_user or deploy_user == "root" or not deploy_dir:
        raise ProjectionError("onramp handoff requires a non-root deploy user and directory")
    if resource.security.password_authentication or resource.security.permit_root_login:
        raise ProjectionError("onramp handoff requires password and root SSH login to remain disabled")

    result["spec"] = {
        "identity": {
            "canonical_resource": service.resource,
            "resource_type": resource.type,
            "hostname": resource.identity.hostname,
        },
        "connection": {
            "address": address,
            "ssh_port": 22,
            "user": deploy_user,
        },
        "substrate": {
            "operating_system": handoff["operating_system"],
            "deployment_root": deploy_dir,
            "container_runtime": handoff["container_runtime"],
            "proxy": handoff["proxy"],
        },
        "authority": {
            "infrastructure_owner": "infra-fabric",
            "application_owner": handoff["consumer"],
            "onramp_permissions": {
                "application_definitions": True,
                "application_lifecycle": True,
                "application_health": True,
                "application_rollback": True,
                "application_data_lifecycle": True,
                "proxmox_lifecycle": False,
                "network_or_storage_mutation": False,
                "host_security_mutation": False,
                "base_proxy_mutation": False,
                "generated_projection_write": False,
            },
        },
    }
    _assert_non_secret(result, "onramp_handoff")
    return result


def render_projection_set(model: CanonicalSite, catalog: ServiceCatalog) -> dict[str, Any]:
    """Render the complete stable non-secret projection set."""
    return {
        "terraform.auto.tfvars.json": render_opentofu_variables(model, catalog),
        "ansible-inventory.json": render_ansible_inventory(model, catalog),
        "ansible-vars.json": render_ansible_vars(model, catalog),
        "dns-records.json": render_dns_records(model),
        "onramp-handoff.json": render_onramp_handoff(model, catalog),
    }


def verify_onramp_handoff_identity(
    model: CanonicalSite,
    catalog: ServiceCatalog,
    handoff: Mapping[str, Any],
) -> None:
    """Fail closed unless the handoff exactly matches canonical identity."""
    if handoff != render_onramp_handoff(model, catalog):
        raise ProjectionError("onramp handoff identity disagrees with the selected canonical model")


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
    hosts: dict[str, Mapping[str, Any]] = {}
    legacy_meta = inventory.get("_meta", {}).get("hostvars", {})
    if isinstance(legacy_meta, Mapping):
        hosts.update({name: values for name, values in legacy_meta.items() if isinstance(values, Mapping)})
    for group in inventory.values():
        if isinstance(group, Mapping) and isinstance(group.get("hosts"), Mapping):
            hosts.update({name: values for name, values in group["hosts"].items() if isinstance(values, Mapping)})
    services = ansible_vars.get("services")
    runtimes = opentofu.get("service_runtime")
    if not isinstance(hosts, Mapping) or not isinstance(services, Mapping) or not isinstance(runtimes, Mapping):
        raise ProjectionError("generated projections have an invalid identity shape")
    runtime_services = set(runtimes)
    if not runtime_services <= set(services):
        raise ProjectionError("service identity sets disagree across projections")
    identities: dict[str, dict[str, str]] = {}
    for name in runtime_services:
        values = services[name]
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
            if isinstance(hostvars, Mapping)
            and (
                hostvars.get("canonical_service") == name
                or name in hostvars.get("canonical_services", [])
            )
        ]
        if len(matching_hosts) != 1 or matching_hosts[0].get("canonical_resource") != resource:
            raise ProjectionError(f"resource identity disagrees across projections: {name}")
        identities[name] = {"resource": resource, "resource_type": resource_type}
    forgejo_scope = (
        services.get("forgejo", {}).get("ansible_vars", {}).get("forgejo_bootstrap_repo_scope")
        if isinstance(services.get("forgejo"), Mapping)
        else None
    )
    runner_scope = (
        services.get("forgejo_runner", {}).get("ansible_vars", {}).get("forgejo_runner_scope")
        if isinstance(services.get("forgejo_runner"), Mapping)
        else None
    )
    if forgejo_scope is not None and runner_scope is not None and forgejo_scope != runner_scope:
        raise ProjectionError(
            "forgejo bootstrap repository and forgejo_runner registration scope disagree"
        )
    return {"site": site, "services": identities, "status": "verified"}


__all__ = [
    "ONRAMP_HANDOFF_API_VERSION",
    "ProjectionError",
    "render_runtime_env",
    "render_ansible_inventory",
    "render_ansible_vars",
    "render_dns_records",
    "render_onramp_handoff",
    "render_opentofu_variables",
    "render_projection_set",
    "verify_cross_projection_identity",
    "verify_onramp_handoff_identity",
]
