variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "do_region" {
  description = "DigitalOcean region"
  type        = string
  default     = "nyc3"
}

variable "droplet_size" {
  description = "Droplet size slug"
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "droplet_image" {
  description = "Droplet OS image"
  type        = string
  default     = "ubuntu-24-04-x64"
}

variable "ssh_key_ids" {
  description = "List of SSH key IDs to add to the droplet"
  type        = list(string)
  default     = []
}

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

variable "db_size" {
  description = "Database cluster size"
  type        = string
  default     = "db-s-1vcpu-1gb"
}

variable "db_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "16"
}

variable "enable_monitoring" {
  description = "Enable droplet monitoring"
  type        = bool
  default     = true
}

variable "enable_backups" {
  description = "Enable droplet backups"
  type        = bool
  default     = true
}

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
