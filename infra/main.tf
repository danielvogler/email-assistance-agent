# Shared resources, one set per project, and one identity, secret and
# service per mailbox. A colleague's mailbox is a separate map entry with its
# own service account, secret and invoker list: nobody can call another
# person's service or read another person's password.

locals {
  # A service only exists once there is an image to run and a password
  # version to run it with. The first apply therefore creates the registry and
  # the empty secrets; see AGENTS.md for the order.
  deployable = {
    for key, mailbox in var.mailboxes : key => mailbox
    if var.image != null && mailbox.secret_version != null
  }

  project_number = data.google_project.this.number
}

data "google_project" "this" {
  project_id = var.project_id
}

# disable_on_destroy is false so that removing this deployment never turns off
# an API something else in the project still uses.
resource "google_project_service" "required" {
  for_each = toset([
    "artifactregistry.googleapis.com", # the image
    "cloudbuild.googleapis.com",       # `make image` builds remotely
    "compute.googleapis.com",          # VPC, NAT and the firewall that blocks SMTP
    "iam.googleapis.com",              # service accounts
    "run.googleapis.com",              # the service and the egress-check job
    "secretmanager.googleapis.com",    # the app passwords
    "storage.googleapis.com",          # the build staging bucket
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.name_prefix
  format        = "DOCKER"
  description   = "Images for ${var.name_prefix}. Deployed by digest only."

  depends_on = [google_project_service.required]
}

# Record every read of a secret. If an app password is ever misused, this is
# how to tell whether it left through Secret Manager.
resource "google_project_iam_audit_config" "secret_reads" {
  project = var.project_id
  service = "secretmanager.googleapis.com"

  audit_log_config {
    log_type = "DATA_READ"
  }
}
