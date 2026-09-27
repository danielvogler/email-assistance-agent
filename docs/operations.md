# Operations

Procedures for a running deployment. First-time setup is in
[AGENTS.md](../AGENTS.md#a-using-this). Every command names the project and
region explicitly; `<values>` come from the operator repository.

## Upgrade

1. In your checkout of this repository, `git fetch --tags` and check out the
   new tag. Read the release notes.
2. `make image PROJECT=<PROJECT> REGION=<REGION>` and put the printed digest in
   `image` in your tfvars.
3. `make infra-plan TFVARS=…` and read the plan: only the image should change,
   unless the release notes say otherwise. Then `make infra-apply TFVARS=…`
   with elevated access.
4. `make verify PROJECT=<PROJECT> REGION=<REGION>`, and record the new commit
   and image in `VERIFICATION.md`.

## Rotate an app password

1. The mailbox owner creates a new app password in their Google account.
2. `read -rs APP_PASSWORD`, then
   `printf '%s' "$APP_PASSWORD" | gcloud secrets versions add email-agent-<key>-app-password --data-file=- --project <PROJECT>`,
   then `unset APP_PASSWORD`
3. Set that mailbox's `secret_version` to the new number; plan and apply.
4. Revoke the old app password in the Google account.
5. `gcloud secrets versions disable <old-version> --secret email-agent-<key>-app-password --project <PROJECT>`
   (as the admin identity: the owner can add versions but not disable them)

Rotate at least yearly, when anyone with access leaves, and at once on any
suspicion.

## Add a mailbox

1. Add an entry to `mailboxes` without `secret_version`; plan and apply. This
   creates its service account and empty secret.
2. The owner adds the app password as above.
3. Set `secret_version`; plan and apply. This creates its service.
4. Run the verification checks for that mailbox and record them.

## Offboard a person

- **Someone who used a mailbox:** remove them from `invoker_members`; plan and
  apply. They can no longer call it.
- **A mailbox owner who leaves:** revoke the app password in their account,
  then remove the mailbox entry and set `deletion_protection = false`; plan,
  check that only that mailbox's resources are destroyed, and apply. Then set
  `deletion_protection` back to true and apply again.

## Suspected misuse

1. **Revoke the app password** in the Google account's security settings.
   This stops every use of it at once, wherever it is.
2. In the Workspace admin console, search the Gmail log for outbound mail
   from the account.
3. Check the Secret Manager Data Access audit logs for reads by anything other
   than the service account, and the Cloud Run logs for unusual tool calls.
4. Rotate as above, then write down what happened.

## Cost

Cloud Run scales to zero and costs close to nothing at this volume. Cloud NAT
has a standing hourly charge plus data: that is the price of routing egress
through a firewall that blocks sending, and it is accepted as such.
