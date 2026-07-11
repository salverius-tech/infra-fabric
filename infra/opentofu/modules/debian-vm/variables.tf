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
  description = "Cloud image import settings."
  type = object({
    datastore_id = string
    url          = string
    file_name    = string
    file_id      = optional(string)
  })
}

variable "disk" {
  description = "VM disk settings."
  type = object({
    datastore_id = string
    size_gb      = number
  })
}

variable "cores" {
  description = "CPU cores."
  type        = number
}

variable "memory_mb" {
  description = "Dedicated memory in MiB."
  type        = number
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
}

variable "ipv4_gateway" {
  description = "IPv4 gateway."
  type        = string
  default     = null
}

variable "cloud_init_user" {
  description = "Cloud-init user created for SSH/bootstrap."
  type        = string
  default     = "root"
}

variable "ssh_public_keys" {
  description = "SSH public keys installed for the cloud-init user."
  type        = list(string)
  default     = []
}

variable "network" {
  description = "Network interface settings."
  type = object({
    bridge      = string
    mac_address = optional(string)
    vlan_id     = optional(number)
  })
}

variable "startup" {
  description = "Proxmox startup order settings."
  type = object({
    order      = string
    up_delay   = string
    down_delay = string
  })
}
