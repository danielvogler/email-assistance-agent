output "image_repository" {
  description = "Push images here, then deploy them by digest."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "secrets" {
  description = "Secret per mailbox. Add the app password with: printf '%s' \"$APP_PASSWORD\" | gcloud secrets versions add <secret> --data-file=- --project <project>"
  value       = { for key, secret in google_secret_manager_secret.app_password : key => secret.secret_id }
}

output "services" {
  description = "Deployed services per mailbox, with the command that connects to each."
  value = {
    for key, service in google_cloud_run_v2_service.mailbox : key => {
      url   = service.uri
      proxy = "gcloud run services proxy ${service.name} --project ${var.project_id} --region ${var.region} --port 8080"
    }
  }
}

output "pending_mailboxes" {
  description = "Mailboxes without a service yet, because image or secret_version is still unset."
  value       = sort([for key in keys(var.mailboxes) : key if !contains(keys(local.deployable), key)])
}

output "egress_check_job" {
  description = "Run with: gcloud run jobs execute <job> --project <project> --region <region> --wait"
  value       = one(google_cloud_run_v2_job.egress_check[*].name)
}

output "build" {
  description = "Identity and bucket `make image` builds with."
  value = {
    service_account = google_service_account.build.email
    bucket          = google_storage_bucket.build.name
  }
}
