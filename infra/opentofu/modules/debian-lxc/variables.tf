variable "description" {
  description = "Human-readable description shown in the Proxmox UI."
  type        = string
}

variable "node_name" {
  description = "Proxmox node that hosts the LXC."
  type        = string
}

variable "vm_id" {
  description = "Proxmox VMID for the LXC."
  type        = number

  validation {
    condition     = var.vm_id == floor(var.vm_id) && var.vm_id >= 100 && var.vm_id <= 999999999
    error_message = "vm_id must be an integer in the Proxmox VMID range 100 through 999999999."
  }
}

variable "started" {
  description = "Whether the LXC should be started."
  type        = bool
  default     = true
}

variable "start_on_boot" {
  description = "Whether the LXC starts automatically when the Proxmox host boots."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Proxmox tags applied to the LXC."
  type        = list(string)
}

variable "cores" {
  description = "CPU cores allocated to the LXC."
  type        = number

  validation {
    condition     = var.cores == floor(var.cores) && var.cores > 0
    error_message = "cores must be a positive integer."
  }
}

variable "memory_mb" {
  description = "Dedicated memory in MiB."
  type        = number

  validation {
    condition     = var.memory_mb == floor(var.memory_mb) && var.memory_mb > 0
    error_message = "memory_mb must be a positive integer."
  }
}

variable "swap_mb" {
  description = "Swap in MiB."
  type        = number
}

variable "features" {
  description = "Container features. keyctl left null keeps the Proxmox default."
  type = object({
    fuse    = optional(bool)
    keyctl  = optional(bool)
    mknod   = optional(bool)
    mount   = optional(list(string))
    nesting = optional(bool, true)
  })
  default = {}
}

variable "device_passthrough" {
  description = "Host devices passed through to the LXC."
  type = list(object({
    path = string
    mode = optional(string)
  }))
  default = []
}

variable "disk" {
  description = "Root filesystem disk settings."
  type = object({
    datastore_id = string
    size_gb      = number
  })

  validation {
    condition     = trimspace(var.disk.datastore_id) != "" && var.disk.size_gb > 0
    error_message = "disk requires a non-empty datastore_id and a positive size_gb."
  }
}

variable "mount_points" {
  description = "Additional mount points for the LXC. Bind mounts use a host path volume; Proxmox-managed volumes use storage_id:size_gb."
  type = list(object({
    volume    = string
    size      = optional(string)
    path      = string
    backup    = optional(bool, false)
    read_only = optional(bool, false)
    acl       = optional(bool, false)
    quota     = optional(bool, false)
    replicate = optional(bool, false)
  }))
  default = []

  validation {
    condition     = alltrue([for mount in var.mount_points : trimspace(mount.volume) != "" && can(regex("^/", mount.path))]) && length(distinct([for mount in var.mount_points : mount.path])) == length(var.mount_points)
    error_message = "mount_points require non-empty volumes and absolute unique guest paths."
  }
}

variable "hostname" {
  description = "Hostname assigned inside the LXC."
  type        = string
}

variable "search_domain" {
  description = "DNS search domain for the LXC."
  type        = string
}

variable "dns_servers" {
  description = "DNS servers used by the LXC."
  type        = list(string)
}

variable "ipv4_address" {
  description = "IPv4 address in CIDR notation, or dhcp."
  type        = string

  validation {
    condition     = var.ipv4_address == "dhcp" || can(cidrhost(var.ipv4_address, 0))
    error_message = "ipv4_address must be dhcp or an IPv4 CIDR address."
  }
}

variable "ipv4_gateway" {
  description = "IPv4 gateway for the LXC."
  type        = string
}

variable "ssh_public_keys" {
  description = "SSH public keys installed for root."
  type        = list(string)

  validation {
    condition     = length(var.ssh_public_keys) > 0
    error_message = "At least one canonical bootstrap SSH public key is required."
  }
}

variable "network" {
  description = "Network interface settings. mac_address left null keeps the Proxmox-generated MAC."
  type = object({
    name        = optional(string, "eth0")
    bridge      = string
    mac_address = optional(string)
    vlan_id     = optional(number)
  })

  validation {
    condition     = trimspace(var.network.bridge) != "" && (try(var.network.mac_address, null) == null || can(regex("^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$", var.network.mac_address))) && (try(var.network.vlan_id, null) == null || (var.network.vlan_id >= 1 && var.network.vlan_id <= 4094))
    error_message = "network requires a bridge; optional mac_address must be colon-delimited and vlan_id must be 1 through 4094."
  }
}

variable "template_file_id" {
  description = "Proxmox file ID of the OS template used to create the LXC."
  type        = string
}

variable "os_type" {
  description = "Operating system type reported to Proxmox."
  type        = string
  default     = "debian"
}

variable "startup" {
  description = "Proxmox startup order and delays."
  type = object({
    order      = string
    up_delay   = string
    down_delay = string
  })
}

variable "wait_for_ipv4" {
  description = "Whether to wait for an IPv4 address before considering the LXC created."
  type        = bool
  default     = true
}
