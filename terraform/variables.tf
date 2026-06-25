# OCI authentication
variable "oci_tenancy_ocid" {
  description = "OCI tenancy OCID"
  type        = string
  sensitive   = true
}

variable "oci_user_ocid" {
  description = "OCI user OCID"
  type        = string
  sensitive   = true
}

variable "oci_fingerprint" {
  description = "OCI API key fingerprint"
  type        = string
  sensitive   = true
}

variable "oci_private_key_path" {
  description = "Path to OCI API private key"
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "oci_region" {
  description = "OCI region"
  type        = string
  default     = "us-ashburn-1"
}

variable "compartment_ocid" {
  description = "OCI compartment OCID"
  type        = string
}

# Project
variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "projectpilot"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = ""
}

# Network
variable "vcn_cidr" {
  description = "VCN CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "Public subnet CIDR block"
  type        = string
  default     = "10.0.1.0/24"
}

# Compute — OCI Always Free: VM.Standard.A1.Flex (ARM, 1 OCPU, 1 GB RAM)
variable "instance_shape" {
  description = "Compute instance shape"
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "instance_ocpus" {
  description = "Number of OCPUs for flex shape"
  type        = number
  default     = 1
}

variable "instance_memory_gbs" {
  description = "Memory in GB for flex shape"
  type        = number
  default     = 1
}

variable "instance_os" {
  description = "Instance OS image"
  type        = string
  default     = "Canonical Ubuntu 24.04"
}

variable "ssh_public_key" {
  description = "SSH public key content for instance access"
  type        = string
  default     = ""
}

variable "enable_monitoring" {
  description = "Enable monitoring"
  type        = bool
  default     = true
}

# App
variable "github_username" {
  description = "GitHub username for GHCR image pulls"
  type        = string
  default     = "ShresthSrivastav"
}

variable "ghcr_token" {
  description = "GitHub Container Registry token"
  type        = string
  sensitive   = true
  default     = ""
}
