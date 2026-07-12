module "forgejo_runner" {
  source = "./modules/debian-lxc"
  count  = local.forgejo_runner_lxc_enabled ? 1 : 0

  description   = var.forgejo_runner_description
  node_name     = var.proxmox_node_name
  vm_id         = var.forgejo_runner_vmid
  started       = var.forgejo_runner_started
  start_on_boot = var.forgejo_runner_start_on_boot
  tags          = ["forgejo", "runner", "actions", "opentofu"]

  cores     = var.forgejo_runner_cores
  memory_mb = var.forgejo_runner_memory_mb
  swap_mb   = var.forgejo_runner_swap_mb

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.forgejo_runner_disk_gb
  }

  hostname      = var.forgejo_runner_hostname
  search_domain = var.forgejo_runner_search_domain
  dns_servers   = var.forgejo_runner_dns_servers
  ipv4_address  = var.forgejo_runner_ipv4_address
  ipv4_gateway  = var.forgejo_runner_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.forgejo_runner_bridge
    mac_address = var.forgejo_runner_mac_address
    vlan_id     = var.forgejo_runner_vlan_id
  }

  template_file_id = proxmox_download_file.debian_13_lxc_template[0].id

  startup = {
    order      = var.forgejo_runner_startup_order
    up_delay   = var.forgejo_runner_startup_up_delay
    down_delay = var.forgejo_runner_startup_down_delay
  }
}

module "forgejo_runner_vm" {
  source = "./modules/debian-vm"
  count  = local.forgejo_runner_enabled && local.forgejo_runner_runtime_type == "vm" ? 1 : 0

  description   = var.forgejo_runner_description
  node_name     = var.proxmox_node_name
  vm_id         = var.forgejo_runner_vmid
  name          = var.forgejo_runner_hostname
  started       = var.forgejo_runner_started
  start_on_boot = var.forgejo_runner_start_on_boot
  tags          = ["forgejo", "runner", "actions", "opentofu"]

  cores     = var.forgejo_runner_cores
  memory_mb = var.forgejo_runner_memory_mb

  image = {
    datastore_id = var.guest_vm_image_datastore_id
    url          = var.guest_vm_image_url
    file_name    = var.guest_vm_image_file_name
    file_id      = local.onramp_host_enabled ? proxmox_download_file.debian_13_onramp_host_image[0].id : proxmox_download_file.debian_13_service_vm_image[0].id
    create       = false
  }

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.forgejo_runner_disk_gb
  }

  search_domain = var.forgejo_runner_search_domain
  dns_servers   = var.forgejo_runner_dns_servers
  ipv4_address  = var.forgejo_runner_ipv4_address
  ipv4_gateway  = var.forgejo_runner_ipv4_gateway

  cloud_init_user = coalesce(try(local.forgejo_runner_runtime.cloud_init_user, null), var.guest_vm_cloud_init_user)
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.forgejo_runner_bridge
    mac_address = var.forgejo_runner_mac_address
    vlan_id     = var.forgejo_runner_vlan_id
  }

  startup = {
    order      = var.forgejo_runner_startup_order
    up_delay   = var.forgejo_runner_startup_up_delay
    down_delay = var.forgejo_runner_startup_down_delay
  }
}
