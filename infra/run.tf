# One private Cloud Run service per mailbox, and the egress-check job.

locals {
  # The Host headers each service accepts (DNS-rebinding protection). The
  # deterministic run.app hostname is used directly on Cloud Run; localhost
  # covers `gcloud run services proxy`.
  allowed_hosts = {
    for key in keys(var.mailboxes) :
    key => join(",", [
      "${var.name_prefix}-${key}-${local.project_number}.${var.region}.run.app",
      "localhost:*",
      "127.0.0.1:*",
    ])
  }
}

resource "google_cloud_run_v2_service" "mailbox" {
  for_each = local.deployable

  project  = var.project_id
  name     = "${var.name_prefix}-${each.key}"
  location = var.region
  # Reachable at its URL, but every request needs an identity token from an
  # invoker below. IAM is the gate, not the network.
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  template {
    service_account                  = google_service_account.mailbox[each.key].email
    max_instance_request_concurrency = 10

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    # ALL_TRAFFIC routes every connection through the VPC, so the SMTP deny
    # rule applies. PRIVATE_RANGES_ONLY would let internet traffic bypass it.
    vpc_access {
      egress = "ALL_TRAFFIC"
      network_interfaces {
        network    = google_compute_network.egress.id
        subnetwork = google_compute_subnetwork.egress.id
      }
    }

    containers {
      image = var.image

      env {
        name  = "EMAIL_USER"
        value = each.value.address
      }
      env {
        name = "EMAIL_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.app_password[each.key].secret_id
            version = each.value.secret_version
          }
        }
      }
      env {
        name  = "READ_LABELS"
        value = join(",", each.value.read_labels)
      }
      env {
        name  = "ALLOWED_HOSTS"
        value = local.allowed_hosts[each.key]
      }
      env {
        name  = "LOG_LEVEL"
        value = var.log_level
      }
      dynamic "env" {
        for_each = each.value.read_max_age_days == null ? [] : [each.value.read_max_age_days]
        content {
          name  = "READ_MAX_AGE_DAYS"
          value = tostring(env.value)
        }
      }
      dynamic "env" {
        for_each = each.value.signature == null ? [] : [each.value.signature]
        content {
          name  = "EMAIL_SIGNATURE"
          value = env.value
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.service_reads,
    google_compute_router_nat.egress,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = {
    for pair in flatten([
      for key, mailbox in local.deployable : [
        for member in mailbox.invoker_members : { key = key, member = member }
      ]
    ]) : "${pair.key}/${pair.member}" => pair
  }

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mailbox[each.value.key].name
  role     = "roles/run.invoker"
  member   = each.value.member
}

# Kept permanently so the check can be re-run after any network change:
#   make verify
resource "google_cloud_run_v2_job" "egress_check" {
  count = var.image == null ? 0 : 1

  project             = var.project_id
  name                = "${var.name_prefix}-egress-check"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.egress_check.email
      max_retries     = 0
      timeout         = "120s"

      vpc_access {
        egress = "ALL_TRAFFIC"
        network_interfaces {
          network    = google_compute_network.egress.id
          subnetwork = google_compute_subnetwork.egress.id
        }
      }

      containers {
        image   = var.image
        command = ["email-assistance-agent-egress-check"]
      }
    }
  }

  depends_on = [google_compute_router_nat.egress]
}
