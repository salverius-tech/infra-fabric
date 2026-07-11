locals {
  service_registry                  = jsondecode(file("${path.module}/../services.json"))
  service_names                     = keys(local.service_registry.services)
  runtime_service_names             = ["technitium", "forgejo", "tailscale_client", "forgejo_runner", "infisical", "hermes", "onramp_host"]
  enabled_services                  = toset(coalesce(var.enabled_services, local.service_registry.default_services))
  invalid_enabled_services          = setsubtract(local.enabled_services, toset(local.service_names))
  invalid_service_runtime_services  = setsubtract(toset(keys(var.service_runtime)), toset(local.runtime_service_names))
  onramp_host_runtime_lxc_requested = contains(keys(var.service_runtime), "onramp_host") && local.onramp_host_runtime_type == "lxc"

  technitium_enabled       = contains(local.enabled_services, "technitium")
  forgejo_enabled          = contains(local.enabled_services, "forgejo")
  tailscale_client_enabled = contains(local.enabled_services, "tailscale_client") && var.tailscale_client_enabled
  forgejo_runner_enabled   = contains(local.enabled_services, "forgejo_runner")
  infisical_enabled        = contains(local.enabled_services, "infisical")
  hermes_enabled           = contains(local.enabled_services, "hermes")
  onramp_host_enabled      = contains(local.enabled_services, "onramp_host")

  technitium_runtime       = lookup(var.service_runtime, "technitium", { type = "lxc", cloud_init_user = null })
  tailscale_client_runtime = lookup(var.service_runtime, "tailscale_client", { type = "lxc", cloud_init_user = null })
  forgejo_runner_runtime   = lookup(var.service_runtime, "forgejo_runner", { type = "lxc", cloud_init_user = null })
  infisical_runtime        = lookup(var.service_runtime, "infisical", { type = "lxc", cloud_init_user = null })
  hermes_runtime           = lookup(var.service_runtime, "hermes", { type = "lxc", cloud_init_user = null })
  onramp_host_runtime      = lookup(var.service_runtime, "onramp_host", { type = "vm", cloud_init_user = null })

  technitium_runtime_type       = local.technitium_runtime.type
  tailscale_client_runtime_type = local.tailscale_client_runtime.type
  forgejo_runner_runtime_type   = local.forgejo_runner_runtime.type
  infisical_runtime_type        = local.infisical_runtime.type
  hermes_runtime_type           = local.hermes_runtime.type
  onramp_host_runtime_type      = local.onramp_host_runtime.type

  technitium_lxc_enabled       = local.technitium_enabled && local.technitium_runtime_type == "lxc"
  tailscale_client_lxc_enabled = local.tailscale_client_enabled && local.tailscale_client_runtime_type == "lxc"
  forgejo_runner_lxc_enabled   = local.forgejo_runner_enabled && local.forgejo_runner_runtime_type == "lxc"
  infisical_lxc_enabled        = local.infisical_enabled && local.infisical_runtime_type == "lxc"
  hermes_lxc_enabled           = local.hermes_enabled && local.hermes_runtime_type == "lxc"

  service_vm_image_enabled = (local.technitium_enabled && local.technitium_runtime_type == "vm") || (local.tailscale_client_enabled && local.tailscale_client_runtime_type == "vm") || (local.forgejo_runner_enabled && local.forgejo_runner_runtime_type == "vm") || (local.infisical_enabled && local.infisical_runtime_type == "vm") || (local.hermes_enabled && local.hermes_runtime_type == "vm")
  lxc_template_enabled     = local.technitium_lxc_enabled || (local.forgejo_enabled && local.forgejo_runtime_type == "lxc") || local.tailscale_client_lxc_enabled || local.forgejo_runner_lxc_enabled || local.infisical_lxc_enabled || local.hermes_lxc_enabled
}

resource "terraform_data" "enabled_services_validation" {
  input = local.enabled_services

  lifecycle {
    precondition {
      condition     = length(local.invalid_enabled_services) == 0
      error_message = "enabled_services may contain only ${join(", ", local.service_names)}."
    }

    precondition {
      condition     = length(local.invalid_service_runtime_services) == 0
      error_message = "service_runtime may contain only guest services: ${join(", ", local.runtime_service_names)}."
    }

    precondition {
      condition     = !local.onramp_host_runtime_lxc_requested
      error_message = "onramp_host is VM-only and does not support service_runtime.onramp_host.type = lxc."
    }
  }
}

moved {
  from = proxmox_download_file.debian_12_lxc_template
  to   = proxmox_download_file.debian_12_lxc_template[0]
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
