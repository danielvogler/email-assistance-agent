# OpenTofu, not Terraform: `tofu plan`, `tofu apply`.
#
# The backend is deliberately empty. Where state lives is the operator's
# decision and is passed at init time from their private repository:
#
#   tofu -chdir=infra init -backend-config=/path/to/backend.hcl
#
# This repository is public, so no bucket, project or mailbox name is ever
# written here.

terraform {
  required_version = ">= 1.8"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.4"
    }
  }

  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
