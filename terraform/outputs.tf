output "compute_id" {
  description = "OCID of the compute instance"
  value       = module.compute.compute_id
}

output "compute_public_ip" {
  description = "Public IP address of the compute instance"
  value       = module.compute.public_ip
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = module.compute.ssh_command
}

output "application_url" {
  description = "Application URL"
  value       = module.compute.application_url
}

output "database_host" {
  description = "PostgreSQL database host"
  value       = module.database.host
}

output "database_port" {
  description = "PostgreSQL database port"
  value       = module.database.port
}

output "database_user" {
  description = "PostgreSQL database user"
  value       = module.database.user
}

output "database_name" {
  description = "PostgreSQL database name"
  value       = module.database.database_name
}

output "database_password" {
  description = "PostgreSQL database password"
  value       = random_password.db_password.result
  sensitive   = true
}

output "database_uri" {
  description = "PostgreSQL connection URI"
  value       = module.database.uri
  sensitive   = true
}
