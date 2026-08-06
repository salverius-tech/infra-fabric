locals {
  service_registry = jsondecode(file("${path.module}/../services.json"))
  service_names    = keys(local.service_registry.services)
  # Canonical selection and runtime are the only root-level service adapters.
  # Individual service aliases stay at consumer boundaries and are derived below.
  runtime_service_metadata = {
    for service_name, entry in local.service_registry.services :
    service_name => entry.runtime
    if entry.runtime_owner != "none" && entry.runtime != null
  }
  runtime_service_names = keys(local.runtime_service_metadata)
  enabled_services      = toset(coalesce(var.enabled_services, local.service_registry.default_services))
  service_enabled = {
    for service_name in local.service_names : service_name => contains(local.enabled_services, service_name)
  }
  service_runtime_by_service = {
    for service_name, metadata in local.runtime_service_metadata :
    service_name => merge(
      { type = metadata.default_type, cloud_init_user = null },
      { for key, value in try(var.service_runtime[service_name], {}) : key => value if value != null },
    )
  }
  invalid_enabled_services         = setsubtract(local.enabled_services, toset(local.service_names))
  invalid_service_runtime_services = setsubtract(toset(keys(var.service_runtime)), toset(local.runtime_service_names))
  invalid_service_runtime_types = {
    for service_name, runtime in local.service_runtime_by_service :
    service_name => runtime.type
    if !contains(local.runtime_service_metadata[service_name].supported_types, runtime.type)
  }
  retained_disabled_services = toset([
    for name, policy in var.stateful_service_disable_policies : name
    if policy == "retain" && !contains(local.enabled_services, name)
  ])
  technitium_required_root_inputs = [
    var.technitium_container_vmid,
    var.technitium_container_hostname,
    var.technitium_container_ipv4_address,
    var.technitium_container_dns_servers,
    var.technitium_container_search_domain,
    var.technitium_container_bridge,
    var.technitium_container_cores,
    var.technitium_container_memory_mb,
    var.technitium_container_disk_gb,
  ]
  forgejo_required_root_inputs = [
    var.forgejo_container_vmid,
    var.forgejo_container_hostname,
    var.forgejo_container_ipv4_address,
    var.forgejo_container_dns_servers,
    var.forgejo_container_search_domain,
    var.forgejo_container_bridge,
    var.forgejo_container_cores,
    var.forgejo_container_memory_mb,
    var.forgejo_container_disk_gb,
    var.forgejo_lan_ip,
    var.forgejo_server_name,
  ]
  onramp_host_runtime_lxc_requested = contains(keys(var.service_runtime), "onramp_host") && local.onramp_host_runtime_type == "lxc"

  technitium_enabled       = local.service_enabled.technitium
  forgejo_enabled          = local.service_enabled.forgejo
  tailscale_client_enabled = local.service_enabled.tailscale_client
  forgejo_runner_enabled   = local.service_enabled.forgejo_runner
  infisical_enabled        = local.service_enabled.infisical
  hermes_enabled           = local.service_enabled.hermes
  sssf_enabled             = local.service_enabled.sssf
  onramp_host_enabled      = local.service_enabled.onramp_host

  technitium_runtime       = local.service_runtime_by_service.technitium
  forgejo_runtime          = local.service_runtime_by_service.forgejo
  tailscale_client_runtime = local.service_runtime_by_service.tailscale_client
  forgejo_runner_runtime   = local.service_runtime_by_service.forgejo_runner
  infisical_runtime        = local.service_runtime_by_service.infisical
  hermes_runtime           = local.service_runtime_by_service.hermes
  sssf_runtime             = local.service_runtime_by_service.sssf
  onramp_host_runtime      = local.service_runtime_by_service.onramp_host

  canonical_operator_access = {
    user        = var.operator_user
    public_keys = var.operator_ssh_public_keys
    dotfiles    = var.operator_dotfiles_repository
    revision    = var.operator_dotfiles_revision
    chezmoi     = var.operator_chezmoi_version
    checksum    = var.operator_chezmoi_sha256
  }

  technitium_runtime_type       = local.technitium_runtime.type
  tailscale_client_runtime_type = local.tailscale_client_runtime.type
  forgejo_runner_runtime_type   = local.forgejo_runner_runtime.type
  infisical_runtime_type        = local.infisical_runtime.type
  hermes_runtime_type           = local.hermes_runtime.type
  sssf_runtime_type             = local.sssf_runtime.type
  onramp_host_runtime_type      = local.onramp_host_runtime.type

  technitium_lxc_enabled       = local.technitium_enabled && local.technitium_runtime_type == "lxc"
  forgejo_lxc_enabled          = local.forgejo_enabled && local.forgejo_runtime_type == "lxc"
  tailscale_client_lxc_enabled = local.tailscale_client_enabled && local.tailscale_client_runtime_type == "lxc"
  forgejo_runner_lxc_enabled   = local.forgejo_runner_enabled && local.forgejo_runner_runtime_type == "lxc"
  infisical_lxc_enabled        = local.infisical_enabled && local.infisical_runtime_type == "lxc"
  hermes_lxc_enabled           = local.hermes_enabled && local.hermes_runtime_type == "lxc"
  sssf_lxc_enabled             = local.sssf_enabled && local.sssf_runtime_type == "lxc"

  service_vm_image_enabled = (local.technitium_enabled && local.technitium_runtime_type == "vm") || (local.forgejo_enabled && local.forgejo_runtime_type == "vm") || (local.tailscale_client_enabled && local.tailscale_client_runtime_type == "vm") || (local.forgejo_runner_enabled && local.forgejo_runner_runtime_type == "vm") || (local.infisical_enabled && local.infisical_runtime_type == "vm") || (local.hermes_enabled && local.hermes_runtime_type == "vm") || (local.sssf_enabled && local.sssf_runtime_type == "vm")
  lxc_template_enabled     = local.technitium_lxc_enabled || (local.forgejo_enabled && local.forgejo_runtime_type == "lxc") || local.tailscale_client_lxc_enabled || local.forgejo_runner_lxc_enabled || local.infisical_lxc_enabled || local.hermes_lxc_enabled || local.sssf_lxc_enabled
}

resource "terraform_data" "enabled_services_validation" {
  input = {
    enabled_services = local.enabled_services
    operator_access  = local.canonical_operator_access
  }

  lifecycle {
    precondition {
      condition     = length(local.invalid_enabled_services) == 0
      error_message = "enabled_services may contain only ${join(", ", local.service_names)}."
    }

    precondition {
      condition     = length(local.invalid_service_runtime_services) == 0
      error_message = "service_runtime may contain only catalog runtime-owning services: ${join(", ", local.runtime_service_names)}."
    }

    precondition {
      condition     = length(local.invalid_service_runtime_types) == 0
      error_message = "service_runtime types must be supported by the catalog: ${jsonencode(local.invalid_service_runtime_types)}."
    }

    precondition {
      condition     = var.forgejo_runtime == null
      error_message = "forgejo_runtime is a retired OpenTofu alias; use service_runtime.forgejo."
    }

    precondition {
      condition     = var.tailscale_client_enabled == null
      error_message = "tailscale_client_enabled is a retired OpenTofu alias; use enabled_services."
    }

    precondition {
      condition     = !local.onramp_host_runtime_lxc_requested
      error_message = "onramp_host is VM-only and does not support service_runtime.onramp_host.type = lxc."
    }

    precondition {
      condition     = length(local.retained_disabled_services) == 0 || var.stateful_destroy_acknowledged
      error_message = "Disabling retained stateful services requires explicit wrapper acknowledgement: ${join(", ", local.retained_disabled_services)}."
    }

    precondition {
      condition     = !local.technitium_enabled || alltrue([for value in local.technitium_required_root_inputs : value != null])
      error_message = "Canonical projections must provide all Technitium root inputs when technitium is enabled."
    }

    precondition {
      condition     = !local.technitium_lxc_enabled || var.technitium_container_swap_mb != null && var.technitium_container_ipv4_gateway != null
      error_message = "Canonical projections must provide Technitium LXC swap and IPv4 gateway when the LXC runtime is enabled."
    }

    precondition {
      condition     = !local.forgejo_enabled || alltrue([for value in local.forgejo_required_root_inputs : value != null])
      error_message = "Canonical projections must provide all Forgejo root inputs when forgejo is enabled."
    }

    precondition {
      condition     = !local.forgejo_lxc_enabled || var.forgejo_container_swap_mb != null
      error_message = "Canonical projections must provide Forgejo LXC swap when the LXC runtime is enabled."
    }
  }
}

moved {
  from = proxmox_download_file.debian_12_lxc_template[0]
  to   = proxmox_download_file.debian_13_lxc_template[0]
}

moved {
  from = proxmox_virtual_environment_container.technitium_dns
  to   = proxmox_virtual_environment_container.technitium_dns[0]
}

moved {
  from = proxmox_virtual_environment_container.forgejo
  to   = proxmox_virtual_environment_container.forgejo[0]
}

moved {
  from = proxmox_virtual_environment_container.technitium_dns[0]
  to   = module.technitium_dns[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.forgejo[0]
  to   = module.forgejo[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.tailscale_client[0]
  to   = module.tailscale_client[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.forgejo_runner[0]
  to   = module.forgejo_runner[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.infisical[0]
  to   = module.infisical[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.hermes[0]
  to   = module.hermes[0].proxmox_virtual_environment_container.this
}
