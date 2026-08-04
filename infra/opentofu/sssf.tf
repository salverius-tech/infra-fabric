module "sssf" {
  source = "./modules/debian-lxc"
  count  = local.sssf_lxc_enabled ? 1 : 0

  description   = var.sssf_description
  node_name     = var.proxmox_node_name
  vm_id         = var.sssf_vmid
  started       = var.sssf_started
  start_on_boot = var.sssf_start_on_boot
  tags          = ["sssf", "software-factory", "opentofu"]

  cores     = var.sssf_cores
  memory_mb = var.sssf_memory_mb
  swap_mb   = var.sssf_swap_mb

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.sssf_disk_gb
  }

  hostname      = var.sssf_hostname
  search_domain = var.sssf_search_domain
  dns_servers   = var.sssf_dns_servers
  ipv4_address  = var.sssf_ipv4_address
  ipv4_gateway  = var.sssf_ipv4_gateway

  ssh_public_keys = lookup(var.bootstrap_ssh_public_keys, "sssf", [])

  network = {
    bridge      = var.sssf_bridge
    mac_address = var.sssf_mac_address
    vlan_id     = var.sssf_vlan_id
  }

  template_file_id = proxmox_download_file.debian_13_lxc_template[0].id

  startup = {
    order      = var.sssf_startup_order
    up_delay   = var.sssf_startup_up_delay
    down_delay = var.sssf_startup_down_delay
  }
}

module "sssf_vm" {
  source = "./modules/debian-vm"
  count  = local.sssf_enabled && local.sssf_runtime_type == "vm" ? 1 : 0

  description   = var.sssf_description
  node_name     = var.proxmox_node_name
  vm_id         = var.sssf_vmid
  name          = var.sssf_hostname
  started       = var.sssf_started
  start_on_boot = var.sssf_start_on_boot
  tags          = ["sssf", "software-factory", "opentofu"]

  cores     = var.sssf_cores
  memory_mb = var.sssf_memory_mb

  image = {
    datastore_id = var.guest_vm_image_datastore_id
    url          = var.guest_vm_image_url
    file_name    = var.guest_vm_image_file_name
    file_id      = local.onramp_host_enabled ? proxmox_download_file.debian_13_onramp_host_image[0].id : proxmox_download_file.debian_13_service_vm_image[0].id
    create       = false
  }

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.sssf_disk_gb
  }

  extra_disks = [{
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.sssf_data_disk_gb
    interface    = "scsi1"
  }]

  search_domain = var.sssf_search_domain
  dns_servers   = var.sssf_dns_servers
  ipv4_address  = var.sssf_ipv4_address
  ipv4_gateway  = var.sssf_ipv4_gateway

  cloud_init_user = var.bootstrap_ssh_user
  ssh_public_keys = lookup(var.bootstrap_ssh_public_keys, "sssf", [])

  network = {
    bridge      = var.sssf_bridge
    mac_address = var.sssf_mac_address
    vlan_id     = var.sssf_vlan_id
  }

  startup = {
    order      = var.sssf_startup_order
    up_delay   = var.sssf_startup_up_delay
    down_delay = var.sssf_startup_down_delay
  }
}
