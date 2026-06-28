output "technitium_container_vmid" {
  description = "Proxmox VMID for the Technitium DNS LXC."
  value       = proxmox_virtual_environment_container.technitium_dns.vm_id
}

output "technitium_dns_ip" {
  description = "Technitium DNS LXC IPv4 address without CIDR suffix."
  value       = split("/", var.container_ipv4_address)[0]
}

output "technitium_web_url" {
  description = "Technitium web console URL after bootstrap install."
  value       = "http://${split("/", var.container_ipv4_address)[0]}:5380/"
}

output "technitium_dns_endpoint" {
  description = "DNS endpoint to use in UniFi DHCP after Technitium is configured."
  value       = "${split("/", var.container_ipv4_address)[0]}:53"
}

output "forgejo_container_vmid" {
  description = "Proxmox VMID for the Forgejo LXC."
  value       = proxmox_virtual_environment_container.forgejo.vm_id
}

output "forgejo_lan_ip" {
  description = "Expected Forgejo LAN IP, usually supplied by static DHCP."
  value       = var.forgejo_lan_ip
}

output "forgejo_https_url" {
  description = "Forgejo HTTPS URL when proxied through Caddy on the Technitium LXC."
  value       = "https://${var.forgejo_server_name}/"
}

output "forgejo_data_mount" {
  description = "Forgejo data bind mount from Proxmox host to LXC."
  value       = "${var.forgejo_data_host_path}:${var.forgejo_data_mount_path}"
}
