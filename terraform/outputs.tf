output "droplet_id" {
  description = "ID of the droplet"
  value       = module.droplet.droplet_id
}

output "droplet_ip" {
  description = "IPv4 address of the droplet"
  value       = module.droplet.droplet_ipv4
}

output "reserved_ip" {
  description = "Reserved IP address"
  value       = module.droplet.reserved_ip
}

output "ssh_command" {
  description = "SSH command to connect to the droplet"
  value       = module.droplet.ssh_command
}

output "application_url" {
  description = "Application URL"
  value       = module.droplet.application_url
}

output "database_host" {
  description = "Database cluster host"
  value       = module.database.host
}

output "database_port" {
  description = "Database cluster port"
  value       = module.database.port
}

output "database_user" {
  description = "Database user"
  value       = module.database.user
}

output "database_name" {
  description = "Database name"
  value       = module.database.database_name
}

output "database_password" {
  description = "Database password"
  value       = random_password.db_password.result
  sensitive   = true
}

output "database_uri" {
  description = "Database connection URI"
  value       = module.database.uri
  sensitive   = true
}
