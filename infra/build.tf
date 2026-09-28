# What `make image` builds with.
#
# In new projects Cloud Build runs as the Compute Engine default service
# account, which in organisations created since May 2024 holds no roles, so a
# plain `gcloud builds submit` fails. This gives builds their own identity with
# exactly two grants: push to this repository, and use this staging bucket.
# The bucket also keeps the uploaded source and build logs in the region.

resource "google_service_account" "build" {
  project      = var.project_id
  account_id   = "${var.name_prefix}-build"
  display_name = "${var.name_prefix} image builds"
  description  = "Runs Cloud Build for the image. Can push to one repository and use one bucket."

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket" "build" {
  project                     = var.project_id
  name                        = "${var.project_id}-${var.name_prefix}-build"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  # Uploaded source and logs are only useful while a build runs.
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.required]
}

# Storage Admin, not objectAdmin: Cloud Build checks the build account against
# a user-created logs bucket and requires this role (Cloud Build docs, "Store
# and manage build logs"). Granted on this bucket only, never the project; the
# bucket is build scratch with a seven-day lifecycle.
resource "google_storage_bucket_iam_member" "build_uses_bucket" {
  bucket = google_storage_bucket.build.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.build.email}"
}

resource "google_artifact_registry_repository_iam_member" "build_pushes" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.build.email}"
}
