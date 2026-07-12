module "tailscale_client" {
  source = "./modules/debian-lxc"
  count  = local.tailscale_client_lxc_enabled ? 1 : 0

  description   = var.tailscale_client_description
  node_name     = var.proxmox_node_name
  vm_id         = var.tailscale_client_vmid
  started       = var.tailscale_client_started
  start_on_boot = var.tailscale_client_start_on_boot
  tags          = ["tailscale", "vpn", "opentofu"]

  cores     = var.tailscale_client_cores
  memory_mb = var.tailscale_client_memory_mb
  swap_mb   = var.tailscale_client_swap_mb

  features = {
    keyctl  = true
    nesting = true
  }

  device_passthrough = [
    {
      path = "/dev/net/tun"
      mode = "0666"
    },
  ]

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.tailscale_client_disk_gb
  }

  hostname      = var.tailscale_client_hostname
  search_domain = var.tailscale_client_search_domain
  dns_servers   = var.tailscale_client_dns_servers
  ipv4_address  = var.tailscale_client_ipv4_address
  ipv4_gateway  = var.tailscale_client_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.tailscale_client_bridge
    mac_address = var.tailscale_client_mac_address
    vlan_id     = var.tailscale_client_vlan_id
  }

  template_file_id = proxmox_download_file.debian_12_lxc_template[0].id

  startup = {
    order      = var.tailscale_client_startup_order
    up_delay   = var.tailscale_client_startup_up_delay
    down_delay = var.tailscale_client_startup_down_delay
  }
}

module "tailscale_client_vm" {
  source = "./modules/debian-vm"
  count  = local.tailscale_client_enabled && local.tailscale_client_runtime_type == "vm" ? 1 : 0

  description   = var.tailscale_client_description
  node_name     = var.proxmox_node_name
  vm_id         = var.tailscale_client_vmid
  name          = var.tailscale_client_hostname
  started       = var.tailscale_client_started
  start_on_boot = var.tailscale_client_start_on_boot
  tags          = ["tailscale", "vpn", "opentofu"]

  cores     = var.tailscale_client_cores
  memory_mb = var.tailscale_client_memory_mb

  image = {
    datastore_id = var.guest_vm_image_datastore_id
    url          = var.guest_vm_image_url
    file_name    = var.guest_vm_image_file_name
    file_id      = local.onramp_host_enabled ? proxmox_download_file.debian_13_onramp_host_image[0].id : proxmox_download_file.debian_13_service_vm_image[0].id
    create       = false
  }

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.tailscale_client_disk_gb
  }

  search_domain = var.tailscale_client_search_domain
  dns_servers   = var.tailscale_client_dns_servers
  ipv4_address  = var.tailscale_client_ipv4_address
  ipv4_gateway  = var.tailscale_client_ipv4_gateway

  cloud_init_user = coalesce(try(local.tailscale_client_runtime.cloud_init_user, null), var.guest_vm_cloud_init_user)
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.tailscale_client_bridge
    mac_address = var.tailscale_client_mac_address
    vlan_id     = var.tailscale_client_vlan_id
  }

  startup = {
    order      = var.tailscale_client_startup_order
    up_delay   = var.tailscale_client_startup_up_delay
    down_delay = var.tailscale_client_startup_down_delay
  }
}
