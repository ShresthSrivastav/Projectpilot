data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_ocid
}

data "oci_core_images" "os" {
  compartment_id           = var.compartment_ocid
  operating_system         = split(" ", var.os)[0]
  operating_system_version = split(" ", var.os)[1]
  shape                    = var.shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_instance" "app" {
  compartment_id      = var.compartment_ocid
  display_name        = "${var.project_name}-${var.environment}"
  shape               = var.shape
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name

  shape_config {
    ocpus         = var.ocpus
    memory_in_gbs = var.memory_gbs
  }

  source_details {
    source_type = "image"
    source_id      = data.oci_core_images.os.images[0].id
  }

  create_vnic_details {
    subnet_id        = var.subnet_id
    display_name     = "${var.project_name}-${var.environment}-vnic"
    assign_public_ip = false
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

data "oci_core_vnic_attachments" "instance_vnics" {
  compartment_id = var.compartment_ocid
  instance_id    = oci_core_instance.app.id
}

data "oci_core_vnic" "instance_vnic" {
  vnic_id = data.oci_core_vnic_attachments.instance_vnics.vnic_attachments[0].vnic_id
}

resource "oci_core_public_ip" "reserved" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.project_name}-${var.environment}-pubip"
  lifetime       = "RESERVED"
  private_ip_id  = data.oci_core_vnic.instance_vnic.private_ip_id

  freeform_tags = var.tags
}
