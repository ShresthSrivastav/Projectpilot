variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "region" {
  type = string
}

variable "size" {
  type = string
}

variable "image" {
  type = string
}

variable "ssh_key_ids" {
  type    = list(string)
  default = []
}

variable "enable_monitoring" {
  type    = bool
  default = true
}

variable "enable_backups" {
  type    = bool
  default = true
}

variable "github_username" {
  type = string
}

variable "ghcr_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type = number
}

variable "db_name" {
  type = string
}

variable "db_user" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "domain_name" {
  type    = string
  default = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
