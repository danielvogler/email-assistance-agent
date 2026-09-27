# Placeholder values only. Copy templates/operator/email-assistance-agent.tfvars.example
# into your private repository and fill that in instead; this file exists so
# `tofu validate` and the tests have something to plan against.
project_id = "example-email-agent"
region     = "europe-west6"

# Leave null on the first apply; set after `make image`.
image = null

mailboxes = {
  alex = {
    address         = "alex@example.com"
    owner_member    = "user:alex@example.com"
    invoker_members = ["user:alex@example.com"]
    secret_version  = null
    signature       = "Alex Example\nExample Ltd"
    read_labels     = ["INBOX", "Clients"]
    # read_max_age_days = 90
  }
}
