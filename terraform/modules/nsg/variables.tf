variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "compartment_ocid" {
  type = string
}

variable "vcn_id" {
  type = string
}

variable "compute_id" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
