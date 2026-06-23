variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "compartment_ocid" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "nsg_ids" {
  type    = list(string)
  default = []
}

variable "shape" {
  type    = string
  default = "VM.Standard.E4.Flex"
}

variable "ocpus" {
  type    = number
  default = 2
}

variable "memory_gbs" {
  type    = number
  default = 8
}

variable "os" {
  type    = string
  default = "Canonical Ubuntu 24.04"
}

variable "ssh_public_key" {
  type    = string
  default = ""
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
