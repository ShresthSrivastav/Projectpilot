resource "oci_psql_db_system" "postgres" {
  display_name    = "${var.project_name}-${var.environment}-db"
  compartment_id  = var.compartment_ocid
  db_version      = var.db_version
  shape           = var.shape
  system_type     = "OCI_OPTIMIZED_STORAGE"

  subnet_id = var.subnet_id

  credentials {
    username = replace("${var.project_name}_admin", "-", "_")
    password = var.db_password
  }

  storage_details {
    is_regionally_durable = true
    capacity_in_gb        = var.storage_gbs
  }

  freeform_tags = var.tags

  lifecycle {
    prevent_destroy = true
  }
}
