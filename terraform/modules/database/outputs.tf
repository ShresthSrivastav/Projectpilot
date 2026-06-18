output "host" {
  value = digitalocean_database_cluster.postgres.host
}

output "port" {
  value = digitalocean_database_cluster.postgres.port
}

output "user" {
  value = digitalocean_database_user.app.name
}

output "password" {
  value     = var.db_password
  sensitive = true
}

output "database_name" {
  value = digitalocean_database_db.app.name
}

output "uri" {
  value     = "postgresql://${digitalocean_database_user.app.name}:${var.db_password}@${digitalocean_database_cluster.postgres.host}:${digitalocean_database_cluster.postgres.port}/${digitalocean_database_db.app.name}?sslmode=require"
  sensitive = true
}

output "cluster_id" {
  value = digitalocean_database_cluster.postgres.id
}
