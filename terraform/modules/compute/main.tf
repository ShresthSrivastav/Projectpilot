terraform {
  required_providers {
    oci = {
      source = "oracle/oci"
    }
  }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_ocid
}

locals {
  os_parts   = split(" ", var.os)
  os_name    = join(" ", slice(local.os_parts, 0, length(local.os_parts) - 1))
  os_version = local.os_parts[length(local.os_parts) - 1]
}

data "oci_core_images" "os" {
  compartment_id           = var.compartment_ocid
  operating_system         = local.os_name
  operating_system_version = local.os_version
  shape                    = var.shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_instance" "app" {
  compartment_id      = var.compartment_ocid
  display_name        = "${var.project_name}-${var.environment}"
  shape               = var.shape
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name

  dynamic "shape_config" {
    for_each = var.shape == "VM.Standard.A1.Flex" ? [1] : []
    content {
      ocpus         = var.ocpus
      memory_in_gbs = var.memory_gbs
    }
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.os.images[0].id
  }

  create_vnic_details {
    subnet_id        = var.subnet_id
    display_name     = "${var.project_name}-${var.environment}-vnic"
    assign_public_ip = true
    nsg_ids          = var.nsg_ids
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/../../cloud-init.yaml", {
      github_username = var.github_username
      ghcr_token      = var.ghcr_token
      domain_name     = var.domain_name
      project_name    = var.project_name
      environment     = var.environment
    }))
  }

  agent_config {
    plugins_config {
      name          = "Compute Instance Monitoring"
      desired_state = var.enable_monitoring ? "ENABLED" : "DISABLED"
    }
  }

  freeform_tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}
