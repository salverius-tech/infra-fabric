resource "terraform_data" "infisical_data_dataset" {
  count = local.infisical_enabled ? 1 : 0

  input = {
    dataset    = var.infisical_data_dataset
    mountpoint = var.infisical_data_host_path
    uid        = var.infisical_data_host_uid
    gid        = var.infisical_data_host_gid
  }

  triggers_replace = {
    dataset    = var.infisical_data_dataset
    mountpoint = var.infisical_data_host_path
    uid        = tostring(var.infisical_data_host_uid)
    gid        = tostring(var.infisical_data_host_gid)
  }

  provisioner "local-exec" {
    interpreter = ["/usr/bin/env", "bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      : "$${PVE_HOST:?PVE_HOST is required}"
      ssh -- "$${PVE_HOST}" bash -s -- \
        "$${INFISICAL_DATA_DATASET}" \
        "$${INFISICAL_DATA_HOST_PATH}" \
        "$${INFISICAL_DATA_HOST_UID}" \
        "$${INFISICAL_DATA_HOST_GID}" <<'REMOTE'
      set -euo pipefail
      dataset="$1"
      mountpoint="$2"
      uid="$3"
      gid="$4"

      if ! zfs list -- "$dataset" >/dev/null 2>&1; then
        zfs create -p -o "mountpoint=$mountpoint" -- "$dataset"
      else
        current_mountpoint="$(zfs get -H -o value mountpoint "$dataset")"
        if [[ "$current_mountpoint" != "$mountpoint" ]]; then
          zfs set "mountpoint=$mountpoint" -- "$dataset"
        fi
      fi
      zfs mount "$dataset" >/dev/null 2>&1 || true
      mkdir -p -- "$mountpoint"
      chown -- "$uid:$gid" "$mountpoint"
      chmod 0750 -- "$mountpoint"
      REMOTE
    EOT

    environment = {
      INFISICAL_DATA_DATASET   = var.infisical_data_dataset
      INFISICAL_DATA_HOST_PATH = var.infisical_data_host_path
      INFISICAL_DATA_HOST_UID  = tostring(var.infisical_data_host_uid)
      INFISICAL_DATA_HOST_GID  = tostring(var.infisical_data_host_gid)
    }
  }
}

resource "proxmox_virtual_environment_container" "infisical" {
  count = local.infisical_enabled ? 1 : 0

  depends_on = [terraform_data.infisical_data_dataset]

  description   = var.infisical_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.infisical_container_vmid
  unprivileged  = true
  started       = var.infisical_started
  start_on_boot = var.infisical_start_on_boot
  tags          = ["infisical", "secrets", "opentofu"]

  cpu {
    cores = var.infisical_container_cores
  }

  memory {
    dedicated = var.infisical_container_memory_mb
    swap      = var.infisical_container_swap_mb
  }

  features {
    nesting = true
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.infisical_container_disk_gb
  }

  mount_point {
    volume = var.infisical_data_host_path
    path   = var.infisical_data_mount_path
  }

  initialization {
    hostname = var.infisical_container_hostname

    dns {
      domain  = var.infisical_container_search_domain
      servers = var.infisical_container_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.infisical_container_ipv4_address
        gateway = var.infisical_container_ipv4_gateway
      }
    }

    user_account {
      password = var.lxc_root_password
      keys     = var.lxc_ssh_public_keys
    }
  }

  network_interface {
    name        = "eth0"
    bridge      = var.infisical_container_bridge
    mac_address = var.infisical_container_mac_address
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template[0].id
    type             = "debian"
  }

  startup {
    order      = var.infisical_startup_order
    up_delay   = var.infisical_startup_up_delay
    down_delay = var.infisical_startup_down_delay
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
