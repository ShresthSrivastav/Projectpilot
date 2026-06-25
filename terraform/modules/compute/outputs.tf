output "compute_id" {
  value = oci_core_instance.app.id
}

output "public_ip" {
  value = oci_core_instance.app.public_ip
}

output "ssh_command" {
  value = "ssh deploy@${oci_core_instance.app.public_ip}"
}

output "application_url" {
  value = var.domain_name != "" ? "https://${var.domain_name}" : "http://${oci_core_instance.app.public_ip}"
}
