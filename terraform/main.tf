locals {
  common_tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

module "droplet" {
  source = "./modules/droplet"

  project_name = var.project_name
  environment  = var.environment
  region       = var.do_region
  size         = var.droplet_size
  image        = var.droplet_image
  ssh_key_ids  = var.ssh_key_ids
  enable_monitoring = var.enable_monitoring
  enable_backups    = var.enable_backups
  github_username   = var.github_username
  ghcr_token        = var.ghcr_token
  db_host           = module.database.host
  db_port           = module.database.port
  db_name           = module.database.database_name
  db_user           = module.database.user
  db_password       = random_password.db_password.result
  domain_name       = var.domain_name
  tags              = local.common_tags
}

module "firewall" {
  source = "./modules/firewall"

  project_name = var.project_name
  environment  = var.environment
  droplet_id   = module.droplet.droplet_id
  tags         = local.common_tags
}

module "database" {
  source = "./modules/database"

  project_name = var.project_name
  environment  = var.environment
  region       = var.do_region
  size         = var.db_size
  version      = var.db_version
  db_password  = random_password.db_password.result
  tags         = local.common_tags
}
