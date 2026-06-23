output "host" {
  value = try(oci_psql_db_system.postgres.endpoints[0].fqdn, oci_psql_db_system.postgres.endpoints[0].ip_address)
}

output "port" {
  value = try(oci_psql_db_system.postgres.endpoints[0].port, 5432)
}

output "user" {
  value = replace("${var.project_name}_admin", "-", "_")
}

output "password" {
  value     = var.db_password
  sensitive = true
}

output "database_name" {
  value = replace("${var.project_name}_db", "-", "_")
}

output "uri" {
  value     = "postgresql://${replace("${var.project_name}_admin", "-", "_")}:${var.db_password}@${try(oci_psql_db_system.postgres.endpoints[0].fqdn, oci_psql_db_system.postgres.endpoints[0].ip_address)}:${try(oci_psql_db_system.postgres.endpoints[0].port, 5432)}/${replace("${var.project_name}_db", "-", "_")}?sslmode=require"
  sensitive = true
}

output "db_system_id" {
  value = oci_psql_db_system.postgres.id
}
