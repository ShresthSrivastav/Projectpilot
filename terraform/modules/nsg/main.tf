terraform {
  required_providers {
    oci = {
      source = "oracle/oci"
    }
  }
}

resource "oci_core_network_security_group" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = var.vcn_id
  display_name   = "${var.project_name}-${var.environment}-nsg"

  freeform_tags = var.tags
}

# Inbound: SSH
resource "oci_core_network_security_group_security_rule" "inbound_ssh" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = "0.0.0.0/0"

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

# Inbound: HTTP
resource "oci_core_network_security_group_security_rule" "inbound_http" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = "0.0.0.0/0"

  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

# Inbound: App (5000)
resource "oci_core_network_security_group_security_rule" "inbound_app" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = "0.0.0.0/0"

  tcp_options {
    destination_port_range {
      min = 5000
      max = 5000
    }
  }
}

# Inbound: HTTPS
resource "oci_core_network_security_group_security_rule" "inbound_https" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = "0.0.0.0/0"

  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# Outbound: All TCP
resource "oci_core_network_security_group_security_rule" "outbound_tcp" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination_type          = "CIDR_BLOCK"
  destination               = "0.0.0.0/0"

  tcp_options {
    destination_port_range {
      min = 1
      max = 65535
    }
  }
}

# Outbound: All UDP
resource "oci_core_network_security_group_security_rule" "outbound_udp" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "17"
  destination_type          = "CIDR_BLOCK"
  destination               = "0.0.0.0/0"

  udp_options {
    destination_port_range {
      min = 1
      max = 65535
    }
  }
}

# Outbound: ICMP
resource "oci_core_network_security_group_security_rule" "outbound_icmp" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "1"
  destination_type          = "CIDR_BLOCK"
  destination               = "0.0.0.0/0"
}
