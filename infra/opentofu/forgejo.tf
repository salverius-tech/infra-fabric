resource "terraform_data" "forgejo_data_dataset" {
  input = {
    dataset    = var.forgejo_data_dataset
    mountpoint = var.forgejo_data_host_path
    uid        = var.forgejo_data_host_uid
    gid        = var.forgejo_data_host_gid
  }

  provisioner "local-exec" {
    command = <<-EOT
      bash -c 'set -euo pipefail
      : "$${PVE_HOST:?PVE_HOST is required}"
      ssh "$${PVE_HOST}" "set -euo pipefail
        if ! zfs list ${var.forgejo_data_dataset} >/dev/null 2>&1; then
          zfs create -o mountpoint=${var.forgejo_data_host_path} ${var.forgejo_data_dataset}
        fi
        mkdir -p ${var.forgejo_data_host_path}
        chown ${var.forgejo_data_host_uid}:${var.forgejo_data_host_gid} ${var.forgejo_data_host_path}
        chmod 0750 ${var.forgejo_data_host_path}
      "'
    EOT
  }
}

resource "proxmox_virtual_environment_container" "forgejo" {
  depends_on = [terraform_data.forgejo_data_dataset]

  description   = var.forgejo_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.forgejo_container_vmid
  unprivileged  = true
  started       = true
  start_on_boot = true
  tags          = ["forgejo", "git", "opentofu"]

  cpu {
    cores = var.forgejo_container_cores
  }

  memory {
    dedicated = var.forgejo_container_memory_mb
    swap      = var.forgejo_container_swap_mb
  }

  features {
    nesting = true
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.forgejo_container_disk_gb
  }

  mount_point {
    volume = var.forgejo_data_host_path
    path   = var.forgejo_data_mount_path
  }

  initialization {
    hostname = var.forgejo_container_hostname

    dns {
      domain  = var.forgejo_container_search_domain
      servers = var.forgejo_container_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.forgejo_container_ipv4_address
        gateway = var.forgejo_container_ipv4_gateway
      }
    }

    user_account {
      password = var.container_root_password
      keys     = var.container_ssh_public_keys
    }
  }

  network_interface {
    name        = "eth0"
    bridge      = var.forgejo_container_bridge
    mac_address = var.forgejo_container_mac_address
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template.id
    type             = "debian"
  }

  startup {
    order      = var.forgejo_startup_order
    up_delay   = var.forgejo_startup_up_delay
    down_delay = var.forgejo_startup_down_delay
  }

  wait_for_ip {
    ipv4 = true
  }

  lifecycle {
    ignore_changes = [
      initialization[0].user_account,
      operating_system[0].template_file_id,
    ]
  }
}
