terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # OCI Object Storage backend (S3-compatible API)
  # Uncomment and configure for remote state:
  # backend "s3" {
  #   bucket                      = "projectpilot-terraform-state"
  #   key                         = "terraform.tfstate"
  #   region                      = var.oci_region
  #   skip_credentials_validation = true
  #   skip_metadata_api_check     = true
  #   skip_requesting_account_id  = true
  #   skip_s3_checksum            = true
  #   endpoints = {
  #     s3 = "https://<namespace>.compat.objectstorage.${var.oci_region}.oraclecloud.com"
  #   }
  # }
}
