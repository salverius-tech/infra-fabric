output "vm_id" {
  description = "Proxmox VMID."
  value       = proxmox_virtual_environment_vm.this.vm_id
}

output "name" {
  description = "VM name."
  value       = proxmox_virtual_environment_vm.this.name
}
