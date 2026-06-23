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

variable "storage_gbs" {
  type    = number
  default = 50
}

variable "db_version" {
  type    = string
  default = "16"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
