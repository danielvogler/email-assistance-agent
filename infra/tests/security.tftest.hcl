# Plan-only checks of the properties the no-send guarantee rests on. They run
# offline against a mocked provider, in CI and with `tofu test`.

mock_provider "google" {
  mock_data "google_project" {
    defaults = {
      number = "123456789012"
    }
  }
}

variables {
  project_id = "test-project"
  image      = "europe-west6-docker.pkg.dev/test-project/email-agent/email-assistance-agent@sha256:0000000000000000000000000000000000000000000000000000000000000000"
  mailboxes = {
    alex = {
      address         = "alex@example.com"
      owner_member    = "user:alex@example.com"
      invoker_members = ["user:alex@example.com"]
      secret_version  = "3"
      read_labels     = ["INBOX", "Clients"]
    }
    sam = {
      address         = "sam@example.com"
      owner_member    = "user:sam@example.com"
      invoker_members = ["user:sam@example.com"]
      secret_version  = "1"
    }
  }
}

run "smtp_submission_ports_are_denied_on_egress" {
  command = plan

  assert {
    condition     = google_compute_firewall.deny_smtp_egress.direction == "EGRESS"
    error_message = "The SMTP rule must apply to egress."
  }
  assert {
    condition     = toset(one(google_compute_firewall.deny_smtp_egress.deny).ports) == toset(["465", "587"])
    error_message = "Ports 465 and 587 must both be denied."
  }
  assert {
    condition     = google_compute_firewall.deny_smtp_egress.priority < 1000
    error_message = "The deny rule must outrank ordinary allow rules."
  }
  assert {
    condition     = contains(google_compute_firewall.deny_smtp_egress.destination_ranges, "0.0.0.0/0")
    error_message = "The deny rule must cover every destination."
  }
}

run "all_service_and_job_traffic_goes_through_the_vpc" {
  command = plan

  assert {
    condition     = alltrue([for s in google_cloud_run_v2_service.mailbox : s.template[0].vpc_access[0].egress == "ALL_TRAFFIC"])
    error_message = "Services must route all traffic through the VPC, or the firewall does not apply."
  }
  assert {
    condition     = google_cloud_run_v2_job.egress_check[0].template[0].template[0].vpc_access[0].egress == "ALL_TRAFFIC"
    error_message = "The egress check must take the same path as the services."
  }
}

run "each_mailbox_is_isolated" {
  command = plan

  assert {
    condition     = length(google_cloud_run_v2_service.mailbox) == 2
    error_message = "Each mailbox gets its own service."
  }
  assert {
    condition     = google_secret_manager_secret_iam_member.service_reads["alex"].member == "serviceAccount:${google_service_account.mailbox["alex"].email}"
    error_message = "A secret must be readable only by its own mailbox's service account."
  }
  assert {
    condition     = google_service_account.mailbox["alex"].account_id != google_service_account.mailbox["sam"].account_id
    error_message = "Mailboxes must not share a service account."
  }
  assert {
    condition     = keys(google_cloud_run_v2_service_iam_member.invokers) == ["alex/user:alex@example.com", "sam/user:sam@example.com"]
    error_message = "Invokers are granted per mailbox only."
  }
  assert {
    condition     = google_secret_manager_secret_iam_member.owner_adds_versions["alex"].role == "roles/secretmanager.secretVersionAdder"
    error_message = "The owner may add a password version but must not be able to read one."
  }
}

run "the_password_is_pinned_and_never_in_state" {
  command = plan

  assert {
    condition = one([
      for e in google_cloud_run_v2_service.mailbox["alex"].template[0].containers[0].env :
      e.value_source[0].secret_key_ref[0].version if e.name == "EMAIL_PASSWORD"
    ]) == "3"
    error_message = "The service must run a pinned secret version."
  }
  assert {
    condition     = one(google_secret_manager_secret.app_password["alex"].replication[0].user_managed[0].replicas).location == "europe-west6"
    error_message = "Secrets stay in the chosen region."
  }
}

run "the_first_apply_creates_no_service" {
  command = plan

  variables {
    image = null
  }

  assert {
    condition     = length(google_cloud_run_v2_service.mailbox) == 0 && length(google_cloud_run_v2_job.egress_check) == 0
    error_message = "Without an image there is nothing to run yet."
  }
  assert {
    condition     = output.pending_mailboxes == tolist(["alex", "sam"])
    error_message = "Pending mailboxes are reported."
  }
}

run "a_mailbox_without_a_password_version_waits" {
  command = plan

  variables {
    mailboxes = {
      alex = {
        address         = "alex@example.com"
        owner_member    = "user:alex@example.com"
        invoker_members = ["user:alex@example.com"]
      }
    }
  }

  assert {
    condition     = length(google_cloud_run_v2_service.mailbox) == 0 && length(google_secret_manager_secret.app_password) == 1
    error_message = "The secret exists before any version does; the service waits for one."
  }
}

run "rejects_public_access" {
  command = plan

  variables {
    mailboxes = {
      alex = {
        address         = "alex@example.com"
        owner_member    = "user:alex@example.com"
        invoker_members = ["allUsers"]
        secret_version  = "1"
      }
    }
  }

  expect_failures = [var.mailboxes]
}

run "rejects_latest_secret_version" {
  command = plan

  variables {
    mailboxes = {
      alex = {
        address         = "alex@example.com"
        owner_member    = "user:alex@example.com"
        invoker_members = ["user:alex@example.com"]
        secret_version  = "latest"
      }
    }
  }

  expect_failures = [var.mailboxes]
}

run "rejects_an_image_tag" {
  command = plan

  variables {
    image = "europe-west6-docker.pkg.dev/test-project/email-agent/email-assistance-agent:latest"
  }

  expect_failures = [var.image]
}

run "services_are_protected_from_deletion_by_default" {
  command = plan

  assert {
    condition     = alltrue([for s in google_cloud_run_v2_service.mailbox : s.deletion_protection])
    error_message = "Services must be protected from accidental deletion unless explicitly turned off."
  }
}

run "builds_have_a_narrow_identity" {
  command = plan

  assert {
    condition     = google_artifact_registry_repository_iam_member.build_pushes.role == "roles/artifactregistry.writer"
    error_message = "The build identity may push images, nothing broader."
  }
  assert {
    condition     = google_storage_bucket_iam_member.build_uses_bucket.role == "roles/storage.admin" && google_storage_bucket_iam_member.build_uses_bucket.bucket == google_storage_bucket.build.name
    error_message = "The build account gets Storage Admin on its own bucket, which Cloud Build requires for a user-created logs bucket."
  }
  assert {
    condition     = google_storage_bucket.build.public_access_prevention == "enforced" && google_storage_bucket.build.location == "europe-west6"
    error_message = "The staging bucket is private and stays in the region."
  }
}

run "services_accept_their_proxy_host" {
  command = plan

  assert {
    condition = strcontains(one([
      for e in google_cloud_run_v2_service.mailbox["alex"].template[0].containers[0].env :
      e.value if e.name == "ALLOWED_HOSTS"
    ]), "email-agent-alex-*-*.a.run.app")
    error_message = "Each service must accept its own legacy run.app host, which gcloud run services proxy uses."
  }
}
