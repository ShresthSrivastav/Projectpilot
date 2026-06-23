locals {
  common_tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

# --- Network Foundation ---

resource "oci_core_vcn" "main" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.project_name}-${var.environment}-vcn"
  cidr_blocks    = [var.vcn_cidr]
  dns_label      = "${var.project_name}${var.environment}"

  freeform_tags = local.common_tags
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project_name}-${var.environment}-igw"
  enabled        = true

  freeform_tags = local.common_tags
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project_name}-${var.environment}-rt-public"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.main.id
  }

  freeform_tags = local.common_tags
}

resource "oci_core_subnet" "public" {
  compartment_id      = var.compartment_ocid
  vcn_id              = oci_core_vcn.main.id
  display_name        = "${var.project_name}-${var.environment}-subnet-public"
  cidr_block          = var.subnet_cidr
  route_table_id      = oci_core_route_table.public.id
  dns_label           = "public"
  prohibit_public_ip_on_vnic = false

  freeform_tags = local.common_tags
}

# --- Secrets ---

resource "random_password" "db_password" {
  length  = 32
  special = false
}

# --- Modules ---

module "nsg" {
  source = "./modules/nsg"

  project_name     = var.project_name
  environment      = var.environment
  compartment_ocid = var.compartment_ocid
  vcn_id           = oci_core_vcn.main.id
  tags             = local.common_tags
}

module "compute" {
  source = "./modules/compute"

  project_name      = var.project_name
  environment       = var.environment
  compartment_ocid  = var.compartment_ocid
  subnet_id         = oci_core_subnet.public.id
  nsg_ids           = [module.nsg.nsg_id]
  shape             = var.instance_shape
  ocpus             = var.instance_ocpus
  memory_gbs        = var.instance_memory_gbs
  os                = var.instance_os
  ssh_public_key    = var.ssh_public_key
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

module "database" {
  source = "./modules/database"

  project_name     = var.project_name
  environment      = var.environment
  compartment_ocid = var.compartment_ocid
  subnet_id        = oci_core_subnet.public.id
  shape            = var.db_shape
  ocpus            = var.db_ocpus
  memory_gbs       = var.db_memory_gbs
  storage_gbs      = var.db_storage_gbs
  db_version       = var.db_version
  db_password      = random_password.db_password.result
  tags             = local.common_tags
}
