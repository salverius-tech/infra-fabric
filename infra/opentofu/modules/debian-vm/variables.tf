variable "description" {
  description = "VM description."
  type        = string
}

variable "node_name" {
  description = "Proxmox node name."
  type        = string
}

variable "vm_id" {
  description = "Proxmox VMID."
  type        = number

  validation {
    condition     = var.vm_id == floor(var.vm_id) && var.vm_id >= 100 && var.vm_id <= 999999999
    error_message = "vm_id must be an integer in the Proxmox VMID range 100 through 999999999."
  }
}

variable "name" {
  description = "VM hostname/name."
  type        = string
}

variable "tags" {
  description = "VM tags."
  type        = list(string)
  default     = []
}

variable "started" {
  description = "Whether the VM should be started."
  type        = bool
  default     = true
}

variable "start_on_boot" {
  description = "Whether Proxmox should start the VM on host boot."
  type        = bool
  default     = true
}

variable "image" {
  description = "Verified cloud image reference managed outside this module."
  type = object({
    datastore_id = string
    url          = string
    file_name    = string
    file_id      = string
    create       = optional(bool, false)
  })

  validation {
    condition     = trimspace(var.image.file_id) != ""
    error_message = "image.file_id must reference a separately checksum-verified Proxmox image."
  }

  validation {
    condition     = !var.image.create
    error_message = "debian-vm does not download images; set image.create=false and provide a checksum-verified image.file_id."
  }
}

variable "disk" {
  description = "VM disk settings."
  type = object({
    datastore_id = string
    size_gb      = number
  })

  validation {
    condition     = trimspace(var.disk.datastore_id) != "" && var.disk.size_gb > 0
    error_message = "disk requires a non-empty datastore_id and a positive size_gb."
  }
}

variable "extra_disks" {
  description = "Additional Proxmox-managed VM disks."
  type = list(object({
    datastore_id = string
    size_gb      = number
    interface    = string
  }))
  default = []

  validation {
    condition     = alltrue([for disk in var.extra_disks : trimspace(disk.datastore_id) != "" && disk.size_gb > 0 && can(regex("^[a-z]+[0-9]+$", disk.interface))])
    error_message = "Each extra disk requires a non-empty datastore_id, positive size_gb, and interface such as scsi1."
  }

  validation {
    condition     = length(distinct([for disk in var.extra_disks : disk.interface])) == length(var.extra_disks)
    error_message = "extra_disks interfaces must be unique."
  }
}

variable "cores" {
  description = "CPU cores."
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

variable "search_domain" {
  description = "DNS search domain."
  type        = string
}

variable "dns_servers" {
  description = "DNS servers."
  type        = list(string)
}

variable "ipv4_address" {
  description = "IPv4 address/CIDR, or dhcp."
  type        = string

  validation {
    condition     = var.ipv4_address == "dhcp" || can(cidrhost(var.ipv4_address, 0))
    error_message = "ipv4_address must be dhcp or an IPv4 CIDR address."
  }
}

variable "ipv4_gateway" {
  description = "IPv4 gateway."
  type        = string
  default     = null

  validation {
    condition     = var.ipv4_gateway == null || can(cidrhost("${var.ipv4_gateway}/32", 0))
    error_message = "ipv4_gateway must be null or an IPv4 address."
  }
}

variable "cloud_init_user" {
  description = "Cloud-init user created for SSH/bootstrap."
  type        = string
  default     = "root"
}

variable "ssh_public_keys" {
  description = "SSH public keys installed for the cloud-init user."
  type        = list(string)

  validation {
    condition     = length(var.ssh_public_keys) > 0
    error_message = "At least one canonical bootstrap SSH public key is required."
  }
}

variable "network" {
  description = "Network interface settings."
  type = object({
    bridge      = string
    mac_address = optional(string)
    vlan_id     = optional(number)
  })

  validation {
    condition     = trimspace(var.network.bridge) != "" && (try(var.network.mac_address, null) == null || can(regex("^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$", var.network.mac_address))) && (try(var.network.vlan_id, null) == null || (var.network.vlan_id >= 1 && var.network.vlan_id <= 4094))
    error_message = "network requires a bridge; optional mac_address must be colon-delimited and vlan_id must be 1 through 4094."
  }
}

variable "startup" {
  description = "Proxmox startup order settings."
  type = object({
    order      = string
    up_delay   = string
    down_delay = string
  })
}
