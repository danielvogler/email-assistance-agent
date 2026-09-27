# Service accounts and the secrets they read.
#
# There is no google_service_account_key and no
# google_secret_manager_secret_version here, and there must never be either:
# both would write key material into state. Cloud Run attaches the identity,
# and the operator pipes the app password straight into Secret Manager.

resource "google_service_account" "mailbox" {
  for_each = var.mailboxes

  project      = var.project_id
  account_id   = "${var.name_prefix}-${each.key}"
  display_name = "${var.name_prefix} (${each.key})"
  description  = "Runs the draft-only MCP service for one mailbox. Reads only that mailbox's app password."

  depends_on = [google_project_service.required]
}

# The egress check needs the same network path as the services, but no secret.
resource "google_service_account" "egress_check" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-egress"
  display_name = "${var.name_prefix} egress check"
  description  = "Runs the job that proves SMTP is blocked. Holds no secret."

  depends_on = [google_project_service.required]
}

# Replicated only in the chosen region, not automatically worldwide, so the
# credential stays where the data-residency decision put it.
resource "google_secret_manager_secret" "app_password" {
  for_each = var.mailboxes

  project   = var.project_id
  secret_id = "${var.name_prefix}-${each.key}-app-password"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "service_reads" {
  for_each = var.mailboxes

  project   = var.project_id
  secret_id = google_secret_manager_secret.app_password[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mailbox[each.key].email}"
}

# The owner can rotate the password without ever being able to read it, which
# keeps it out of reach of the coding agent that runs as the owner.
resource "google_secret_manager_secret_iam_member" "owner_adds_versions" {
  for_each = var.mailboxes

  project   = var.project_id
  secret_id = google_secret_manager_secret.app_password[each.key].secret_id
  role      = "roles/secretmanager.secretVersionAdder"
  member    = each.value.owner_member
}
