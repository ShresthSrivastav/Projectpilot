resource "digitalocean_droplet" "app" {
  name   = "${var.project_name}-${var.environment}"
  region = var.region
  size   = var.size
  image  = var.image

  ssh_keys = var.ssh_key_ids

  monitoring = var.enable_monitoring
  backups    = var.enable_backups

  user_data = templatefile("${path.module}/../../cloud-init.yaml", {
    github_username = var.github_username
    ghcr_token      = var.ghcr_token
    db_host         = var.db_host
    db_port         = var.db_port
    db_name         = var.db_name
    db_user         = var.db_user
    db_password     = var.db_password
    domain_name     = var.domain_name
    project_name    = var.project_name
    environment     = var.environment
  })

  tags = values(var.tags)

  lifecycle {
    create_before_destroy = true
  }
}

resource "digitalocean_reserved_ip" "app" {
  region = var.region
}

resource "digitalocean_reserved_ip_assignment" "app" {
  ip_address = digitalocean_reserved_ip.app.ip_address
  droplet_id = digitalocean_droplet.app.id
}

data "digitalocean_ssh_key" "default" {
  count = length(var.ssh_key_ids) > 0 ? 1 : 0
  id    = var.ssh_key_ids[0]
}
