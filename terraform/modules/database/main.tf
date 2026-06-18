resource "digitalocean_database_cluster" "postgres" {
  name       = "${var.project_name}-${var.environment}-db"
  engine     = "pg"
  version    = var.version
  size       = var.size
  region     = var.region
  node_count = 1

  tags = values(var.tags)
}

resource "digitalocean_database_user" "app" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "${var.project_name}_app"

  role {
    role = "doadmin"
  }
}

resource "digitalocean_database_db" "app" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = var.project_name
}

resource "digitalocean_database_firewall" "app" {
  cluster_id = digitalocean_database_cluster.postgres.id

  rule {
    type    = "tag"
    value   = "${var.project_name}-${var.environment}"
  }
}
