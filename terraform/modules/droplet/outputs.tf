output "droplet_id" {
  value = digitalocean_droplet.app.id
}

output "droplet_ipv4" {
  value = digitalocean_droplet.app.ipv4_address
}

output "reserved_ip" {
  value = digitalocean_reserved_ip.app.ip_address
}

output "ssh_command" {
  value = "ssh root@${digitalocean_reserved_ip.app.ip_address}"
}

output "application_url" {
  value = var.domain_name != "" ? "https://${var.domain_name}" : "http://${digitalocean_reserved_ip.app.ip_address}"
}
