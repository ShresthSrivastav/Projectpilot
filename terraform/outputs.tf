output "instance_id" {
  description = "OCID of the compute instance"
  value       = module.compute.compute_id
}

output "instance_public_ip" {
  description = "Public IP address of the compute instance"
  value       = module.compute.public_ip
}

output "ssh_connection_string" {
  description = "SSH command to connect to the instance"
  value       = module.compute.ssh_command
}

output "application_url" {
  description = "Application URL"
  value       = module.compute.application_url
}
