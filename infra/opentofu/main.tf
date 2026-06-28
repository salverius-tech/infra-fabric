resource "proxmox_download_file" "debian_12_lxc_template" {
  content_type        = "vztmpl"
  datastore_id        = var.template_datastore_id
  file_name           = var.debian_template_file_name
  node_name           = var.proxmox_node_name
  url                 = var.debian_template_url
  overwrite           = false
  overwrite_unmanaged = false
}

resource "proxmox_virtual_environment_container" "technitium_dns" {
  description   = var.container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.container_vmid
  unprivileged  = true
  started       = true
  start_on_boot = true
  tags          = ["dns", "technitium", "opentofu"]

  cpu {
    cores = var.container_cores
  }

  memory {
    dedicated = var.container_memory_mb
    swap      = var.container_swap_mb
  }

  features {
    nesting = true
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.container_disk_gb
  }

  initialization {
    hostname = var.container_hostname

    dns {
      domain  = var.container_search_domain
      servers = var.container_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.container_ipv4_address
        gateway = var.container_ipv4_gateway
      }
    }

    user_account {
      password = var.container_root_password
      keys     = var.container_ssh_public_keys
    }
  }

  network_interface {
    name   = "eth0"
    bridge = var.container_bridge
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template.id
    type             = "debian"
  }

  startup {
    order      = "1"
    up_delay   = "15"
    down_delay = "15"
  }

  wait_for_ip {
    ipv4 = true
  }
}
