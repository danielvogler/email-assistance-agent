# The network half of "it cannot send".
#
# Cloud Run egresses through this VPC for all traffic, so the firewall below
# applies to every connection the service opens. Google Cloud already blocks
# tcp/25; this denies the submission ports 465 and 587, which are open by
# default. An app password cannot use the Gmail REST API, so with SMTP closed
# the credential has no route left that sends.

resource "google_compute_network" "egress" {
  project                 = var.project_id
  name                    = var.name_prefix
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "egress" {
  project                  = var.project_id
  name                     = var.name_prefix
  region                   = var.region
  network                  = google_compute_network.egress.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

# Priority 100 beats the implied allow-all egress rule (65535) and any
# ordinary allow rule someone adds later at the default 1000.
# If this VPC ever gets IPv6 egress, mirror this rule for ::/0.
resource "google_compute_firewall" "deny_smtp_egress" {
  project            = var.project_id
  name               = "${var.name_prefix}-deny-smtp-egress"
  network            = google_compute_network.egress.id
  direction          = "EGRESS"
  priority           = 100
  destination_ranges = ["0.0.0.0/0"]

  deny {
    protocol = "tcp"
    ports    = ["465", "587"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# Internet egress for everything else, which in practice is imap.gmail.com.
# NAT is the standing cost of this design; it buys the network guarantee.
resource "google_compute_router" "egress" {
  project = var.project_id
  name    = var.name_prefix
  region  = var.region
  network = google_compute_network.egress.id
}

resource "google_compute_router_nat" "egress" {
  project                            = var.project_id
  name                               = var.name_prefix
  router                             = google_compute_router.egress.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.egress.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
}
