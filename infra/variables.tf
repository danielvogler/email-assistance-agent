variable "project_id" {
  description = "A project dedicated to this service. In a shared project, whoever holds Owner there can read every mailbox secret, which defeats the isolation."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, the subnet, NAT, Artifact Registry and secret replicas. Pick it for data residency."
  type        = string
  default     = "europe-west6"
}

variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
  default     = "email-agent"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,13}$", var.name_prefix))
    error_message = "name_prefix must be 3-14 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "image" {
  description = "Container image pinned by digest (…/email-assistance-agent@sha256:…). Leave null on the first apply: the registry has to exist before an image can be pushed to it."
  type        = string
  default     = null

  validation {
    condition     = var.image == null || can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be pinned by digest (@sha256:...), never a tag: a tag can be moved onto other code."
  }
}

variable "subnet_cidr" {
  description = "Range for the subnet Cloud Run egresses through. Small is fine: two instances per mailbox at most."
  type        = string
  default     = "10.10.0.0/26"
}

variable "max_instances" {
  description = "Cloud Run instances per mailbox. Gmail allows about 15 concurrent IMAP connections per account."
  type        = number
  default     = 2
}

variable "deletion_protection" {
  description = "Stops an apply from deleting a mailbox's service. Set false only for the apply that removes a mailbox, then back."
  type        = bool
  default     = true
}

variable "log_level" {
  description = "Log level for the service."
  type        = string
  default     = "INFO"
}

variable "mailboxes" {
  description = <<-EOT
    One entry per mailbox, keyed by a short name that becomes part of resource names.
      address           the Gmail or Workspace address
      owner_member      who may store a new app password (e.g. "user:you@example.com"); they cannot read one back
      invoker_members   who may call this mailbox's service
      secret_version    the app password version to run with; null until one has been added
      signature         appended below every draft
      read_labels       labels the service may read; empty means all
      read_max_age_days how far back it may read; null means no limit
  EOT
  type = map(object({
    address           = string
    owner_member      = string
    invoker_members   = list(string)
    secret_version    = optional(string)
    signature         = optional(string)
    read_labels       = optional(list(string), [])
    read_max_age_days = optional(number)
  }))

  validation {
    condition     = alltrue([for key in keys(var.mailboxes) : can(regex("^[a-z][a-z0-9-]{0,14}$", key))])
    error_message = "Mailbox keys must be 1-15 lowercase letters, digits or hyphens, starting with a letter, so service account ids stay within 30 characters."
  }

  validation {
    condition     = alltrue([for m in values(var.mailboxes) : can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", m.address))])
    error_message = "Every mailbox address must be an email address."
  }

  validation {
    condition     = alltrue([for m in values(var.mailboxes) : m.secret_version == null || can(regex("^[0-9]+$", m.secret_version))])
    error_message = "secret_version must be a version number, never \"latest\": rotation should be an explicit, reviewed apply."
  }

  validation {
    condition = alltrue(flatten([
      for m in values(var.mailboxes) : [
        for member in concat(m.invoker_members, [m.owner_member]) :
        !contains(["allUsers", "allAuthenticatedUsers"], member)
      ]
    ]))
    error_message = "allUsers and allAuthenticatedUsers are never allowed: the service reads a mailbox."
  }
}
