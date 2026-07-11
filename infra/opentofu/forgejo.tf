locals {
  forgejo_default_data_storage = {
    type          = "none"
    source        = null
    create_source = true
    host_uid      = 100000
    host_gid      = 100000
    mode          = "0750"
    host_prepare = {
      type             = "directory"
      dataset          = null
      mountpoint       = null
      server           = null
      export           = null
      share            = null
      credentials_file = null
      options          = []
    }
    storage_id       = null
    size_gb          = null
    acl              = false
    quota            = false
    replicate        = false
    server           = null
    export           = null
    share            = null
    credentials_file = null
    options          = []
    owner            = null
    group            = null
    mount_unit       = true
    target           = null
    backup           = false
    read_only        = false
  }
  forgejo_runtime        = lookup(var.service_runtime, "forgejo", { type = var.forgejo_runtime.type, cloud_init_user = null })
  forgejo_runtime_type   = local.forgejo_runtime.type
  forgejo_storage        = lookup(var.service_storage, "forgejo", {})
  forgejo_data_storage   = lookup(local.forgejo_storage, "data", local.forgejo_default_data_storage)
  forgejo_data_mountable = contains(["bind", "proxmox_volume"], local.forgejo_data_storage.type)
  forgejo_data_volume = (
    local.forgejo_data_storage.type == "bind" ? local.forgejo_data_storage.source :
    local.forgejo_data_storage.type == "proxmox_volume" ? local.forgejo_data_storage.storage_id :
    null
  )
  forgejo_data_size = local.forgejo_data_storage.type == "proxmox_volume" ? format("%dG", local.forgejo_data_storage.size_gb) : null
  forgejo_guest_mount_features = compact([
    local.forgejo_data_storage.type == "guest_nfs" ? "nfs" : "",
    local.forgejo_data_storage.type == "guest_cifs" ? "cifs" : "",
  ])
}

resource "terraform_data" "forgejo_storage_validation" {
  count = local.forgejo_enabled ? 1 : 0

  input = {
    runtime  = { type = local.forgejo_runtime_type }
    storage  = local.forgejo_data_storage
    database = var.forgejo_database
  }

  lifecycle {
    precondition {
      condition     = contains(["bind", "proxmox_volume", "guest_nfs", "guest_cifs"], local.forgejo_data_storage.type)
      error_message = "Forgejo requires service_storage.forgejo.data to define durable storage."
    }

    precondition {
      condition     = !(contains(["guest_nfs", "guest_cifs"], local.forgejo_data_storage.type) && local.forgejo_data_storage.target == "/var/lib/forgejo" && var.forgejo_database.type == "sqlite")
      error_message = "Do not place Forgejo SQLite on guest network storage. Set forgejo_database.type to postgres or mount only non-database Forgejo paths."
    }
  }
}

module "forgejo" {
  source = "./modules/debian-lxc"
  count  = local.forgejo_enabled && local.forgejo_runtime_type == "lxc" ? 1 : 0

  description = var.forgejo_container_description
  node_name   = var.proxmox_node_name
  vm_id       = var.forgejo_container_vmid
  tags        = ["forgejo", "git", "opentofu"]

  cores     = var.forgejo_container_cores
  memory_mb = var.forgejo_container_memory_mb
  swap_mb   = var.forgejo_container_swap_mb

  features = length(local.forgejo_guest_mount_features) > 0 ? {
    mount = local.forgejo_guest_mount_features
  } : {}

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.forgejo_container_disk_gb
  }

  mount_points = local.forgejo_data_mountable ? [
    {
      volume    = local.forgejo_data_volume
      size      = local.forgejo_data_size
      path      = local.forgejo_data_storage.target
      backup    = local.forgejo_data_storage.backup
      read_only = local.forgejo_data_storage.read_only
      acl       = local.forgejo_data_storage.acl
      quota     = local.forgejo_data_storage.quota
      replicate = local.forgejo_data_storage.replicate
    },
  ] : []

  hostname      = var.forgejo_container_hostname
  search_domain = var.forgejo_container_search_domain
  dns_servers   = var.forgejo_container_dns_servers
  ipv4_address  = var.forgejo_container_ipv4_address
  ipv4_gateway  = var.forgejo_container_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.forgejo_container_bridge
    mac_address = var.forgejo_container_mac_address
    vlan_id     = var.forgejo_container_vlan_id
  }

  template_file_id = proxmox_download_file.debian_12_lxc_template[0].id

  startup = {
    order      = var.forgejo_startup_order
    up_delay   = var.forgejo_startup_up_delay
    down_delay = var.forgejo_startup_down_delay
  }

  depends_on = [terraform_data.forgejo_storage_validation]
}

module "forgejo_vm" {
  source = "./modules/debian-vm"
  count  = local.forgejo_enabled && local.forgejo_runtime_type == "vm" ? 1 : 0

  description = var.forgejo_container_description
  node_name   = var.proxmox_node_name
  vm_id       = var.forgejo_container_vmid
  name        = var.forgejo_container_hostname
  tags        = ["forgejo", "git", "opentofu"]

  cores     = var.forgejo_container_cores
  memory_mb = var.forgejo_container_memory_mb

  image = {
    datastore_id = var.forgejo_vm_image_datastore_id
    url          = var.forgejo_vm_image_url
    file_name    = var.forgejo_vm_image_file_name
    file_id      = local.onramp_host_enabled ? proxmox_download_file.debian_13_onramp_host_image[0].id : null
  }

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.forgejo_container_disk_gb
  }

  search_domain = var.forgejo_container_search_domain
  dns_servers   = var.forgejo_container_dns_servers
  ipv4_address  = var.forgejo_container_ipv4_address
  ipv4_gateway  = var.forgejo_container_ipv4_gateway

  cloud_init_user = var.forgejo_vm_cloud_init_user
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.forgejo_container_bridge
    mac_address = var.forgejo_container_mac_address
    vlan_id     = var.forgejo_container_vlan_id
  }

  startup = {
    order      = var.forgejo_startup_order
    up_delay   = var.forgejo_startup_up_delay
    down_delay = var.forgejo_startup_down_delay
  }

  depends_on = [terraform_data.forgejo_storage_validation]
}
