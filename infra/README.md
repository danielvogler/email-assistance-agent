# infra

OpenTofu for every Google Cloud resource the service needs. It holds no real
values: the operator passes a tfvars file and a backend config from their own
private repository. [AGENTS.md](../AGENTS.md) walks through the whole
deployment; this page is the reference.

## What it creates

Once per project:

- the required APIs, an Artifact Registry repository, and a Data Access audit
  log for every Secret Manager read
- a VPC and subnet, Cloud NAT for internet egress, and a firewall rule that
  denies outbound tcp 465 and 587
- the `egress-check` Cloud Run job, which proves that rule works
- a build service account and a regional staging bucket for `make image`,
  because Cloud Build's default identity has no roles in new projects

Per mailbox (one entry in `mailboxes`):

- a service account and an app-password secret that only it can read; the
  mailbox owner may add versions but not read them
- a private Cloud Run service with all egress routed through the VPC, invokable
  only by that mailbox's `invoker_members`

Nothing here creates a service account key or a secret version, and a test
fails if either appears: both would put key material into state.

## Staged apply

A service needs an image and a password version, and neither can exist
before the first apply creates the registry and the secret:

1. Apply with `image = null`. This creates the registry, secrets and network.
2. `make image`, and add the app password to each secret.
3. Set `image` (by digest) and each `secret_version`, then apply again.

`pending_mailboxes` in the outputs lists mailboxes still waiting for step 3.

## Inputs

| Name | Default | Meaning |
|---|---|---|
| `project_id` | | A dedicated project |
| `region` | `europe-west6` | Where everything runs and the secrets are replicated |
| `name_prefix` | `email-agent` | Prefix for every resource name |
| `image` | `null` | Image pinned by digest; null until the first build |
| `subnet_cidr` | `10.10.0.0/26` | Subnet range for egress |
| `max_instances` | `2` | Cloud Run instances per mailbox |
| `deletion_protection` | `true` | Blocks deleting a service; false only for the apply that removes a mailbox |
| `log_level` | `INFO` | Service log level |
| `mailboxes` | | Map of mailboxes; see `variables.tf` for the fields |

## Outputs

`image_repository`, `secrets`, `services` (URL and proxy command per mailbox),
`pending_mailboxes`, `egress_check_job`, `build`.

## Tests

```bash
tofu -chdir=infra init -backend=false
tofu -chdir=infra test
```

The tests plan against a mocked provider, offline, and check the properties the
no-send guarantee depends on: SMTP denied on egress, all traffic through the
VPC, per-mailbox isolation, pinned secret versions, and no public access.
