locals {
  image_file_id = var.image.file_id
}

resource "proxmox_virtual_environment_vm" "this" {
  name        = var.name
  description = var.description
  node_name   = var.node_name
  vm_id       = var.vm_id
  tags        = var.tags

  started         = var.started
  on_boot         = var.start_on_boot
  stop_on_destroy = true

  agent {
    enabled = false
  }

  cpu {
    cores = var.cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = var.memory_mb
  }

  disk {
    datastore_id = var.disk.datastore_id
    import_from  = local.image_file_id
    interface    = "scsi0"
    size         = var.disk.size_gb
  }

  dynamic "disk" {
    for_each = var.extra_disks
    content {
      datastore_id = disk.value.datastore_id
      interface    = disk.value.interface
      size         = disk.value.size_gb
    }
  }

  initialization {
    datastore_id = var.disk.datastore_id

    dns {
      domain  = var.search_domain
      servers = var.dns_servers
    }

    ip_config {
      ipv4 {
        address = var.ipv4_address
        gateway = var.ipv4_gateway
      }
    }

    user_account {
      username = var.cloud_init_user
      keys     = var.ssh_public_keys
    }
  }

  network_device {
    bridge      = var.network.bridge
    mac_address = var.network.mac_address
    vlan_id     = var.network.vlan_id
  }

  operating_system {
    type = "l26"
  }

  serial_device {}

  vga {
    type = "serial0"
  }

  startup {
    order      = var.startup.order
    up_delay   = var.startup.up_delay
    down_delay = var.startup.down_delay
  }
}
