output "compute_id" {
  value = oci_core_instance.app.id
}

output "public_ip" {
  value = oci_core_public_ip.reserved.ip_address
}

output "ssh_command" {
  value = "ssh ubuntu@${oci_core_public_ip.reserved.ip_address}"
}

output "application_url" {
  value = var.domain_name != "" ? "https://${var.domain_name}" : "http://${oci_core_public_ip.reserved.ip_address}"
}

output "vnic_attachment" {
  value = oci_core_instance.app.vnic_attachments[0]
}
