resource "proxmox_download_file" "debian_13_lxc_template" {
  count = local.lxc_template_enabled ? 1 : 0

  content_type        = "vztmpl"
  datastore_id        = var.template_datastore_id
  file_name           = var.debian_template_file_name
  node_name           = var.proxmox_node_name
  url                 = var.debian_template_url
  checksum            = var.debian_template_checksum
  checksum_algorithm  = var.debian_template_checksum_algorithm
  upload_timeout      = var.lxc_template_download_timeout_seconds
  overwrite           = false
  overwrite_unmanaged = false
}

resource "proxmox_download_file" "debian_13_service_vm_image" {
  count = local.service_vm_image_enabled && !local.onramp_host_enabled ? 1 : 0

  content_type        = "import"
  datastore_id        = var.guest_vm_image_datastore_id
  file_name           = var.guest_vm_image_file_name
  node_name           = var.proxmox_node_name
  url                 = var.guest_vm_image_url
  checksum            = var.guest_vm_image_checksum
  checksum_algorithm  = var.guest_vm_image_checksum_algorithm
  overwrite           = false
  overwrite_unmanaged = false
}

module "technitium_dns" {
  source = "./modules/debian-lxc"
  count  = local.technitium_lxc_enabled ? 1 : 0

  description = var.technitium_container_description
  node_name   = var.proxmox_node_name
  vm_id       = var.technitium_container_vmid
  tags        = ["dns", "technitium", "opentofu"]

  cores     = var.technitium_container_cores
  memory_mb = var.technitium_container_memory_mb
  swap_mb   = var.technitium_container_swap_mb

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.technitium_container_disk_gb
  }

  hostname      = var.technitium_container_hostname
  search_domain = var.technitium_container_search_domain
  dns_servers   = var.technitium_container_dns_servers
  ipv4_address  = var.technitium_container_ipv4_address
  ipv4_gateway  = var.technitium_container_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge  = var.technitium_container_bridge
    vlan_id = var.technitium_container_vlan_id
  }

  template_file_id = proxmox_download_file.debian_13_lxc_template[0].id

  startup = {
    order      = "1"
    up_delay   = "15"
    down_delay = "15"
  }
}

module "technitium_dns_vm" {
  source = "./modules/debian-vm"
  count  = local.technitium_enabled && local.technitium_runtime_type == "vm" ? 1 : 0

  description = var.technitium_container_description
  node_name   = var.proxmox_node_name
  vm_id       = var.technitium_container_vmid
  name        = var.technitium_container_hostname
  tags        = ["dns", "technitium", "opentofu"]

  cores     = var.technitium_container_cores
  memory_mb = var.technitium_container_memory_mb

  image = {
    datastore_id = var.guest_vm_image_datastore_id
    url          = var.guest_vm_image_url
    file_name    = var.guest_vm_image_file_name
    file_id      = local.onramp_host_enabled ? proxmox_download_file.debian_13_onramp_host_image[0].id : proxmox_download_file.debian_13_service_vm_image[0].id
    create       = false
  }

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.technitium_container_disk_gb
  }

  search_domain = var.technitium_container_search_domain
  dns_servers   = var.technitium_container_dns_servers
  ipv4_address  = var.technitium_container_ipv4_address
  ipv4_gateway  = var.technitium_container_ipv4_gateway

  cloud_init_user = coalesce(try(local.technitium_runtime.cloud_init_user, null), var.guest_vm_cloud_init_user)
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge  = var.technitium_container_bridge
    vlan_id = var.technitium_container_vlan_id
  }

  startup = {
    order      = "1"
    up_delay   = "15"
    down_delay = "15"
  }
}
