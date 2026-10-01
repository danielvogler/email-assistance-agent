# email-assistance-agent: verification record

Fill this in after every first deployment and after any change to the network,
IAM or image. The service is not used for real mail until every line passes.

- Repository commit deployed: `REPLACE`
- Image: `REPLACE@sha256:…`
- Project / region: `REPLACE` / `REPLACE`

| # | Check | How | Result | Date | By |
|---|---|---|---|---|---|
| 1 | SMTP 465/587 blocked, IMAP 993 open from the service network | `make verify PROJECT=… REGION=…` exits 0 | | | |
| 2 | Tool list is exactly search, read_message, read_thread, list_drafts, read_draft, create_draft, compose_draft, update_draft, delete_draft | MCP client, through `make proxy` | | | |
| 3 | A draft lands in the original thread with correct To/Cc/Subject; the original stays unread | `create_draft` on a test message, then check Gmail | | | |
| 4 | The everyday identity cannot read the secret | `gcloud secrets versions access latest --secret … --project …` → PERMISSION_DENIED | | | |
| 5 | The everyday identity cannot deploy | `gcloud run deploy email-agent-<key> --image <IMAGE> --region … --project …` → PERMISSION_DENIED | | | |
| 6 | Secret reads are audit-logged | Cloud Logging: Secret Manager data-access entry for the service account at instance start | | | |
| 7 | Data-protection sign-off recorded | link to the decision in DECISIONS.md | | | |
