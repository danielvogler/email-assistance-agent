# Security

## Reporting

Report a vulnerability privately through
[GitHub security advisories](https://github.com/danielvogler/email-assistance-agent/security/advisories/new).
Please do not open a public issue for anything exploitable.

## What this repository is careful about

It puts a mailbox within reach of a coding agent, so the guards are the
product rather than a nicety.

### It cannot send

A person sends every email. The service is built so that it has no way to,
whatever the code, the model or the agent driving it does:

| Layer | Control | Checked by |
|---|---|---|
| Credential | A Gmail app password: IMAP and SMTP only, no Gmail REST API | Google's documentation |
| Network | All Cloud Run egress goes through a VPC whose firewall denies tcp 465 and 587; Google Cloud blocks 25 | the `egress-check` job (`make verify`); OpenTofu tests |
| Code | No SMTP or send call in `src/`; exactly eight tools; none sends or moves mail, and the only deletion is of drafts the service created itself | a pre-commit hook; the tool allowlist test |

Why an app password and not OAuth: every Gmail scope that can create drafts
can also send (`gmail.compose`, `gmail.modify`), and IMAP over OAuth needs the
full `mail.google.com` scope, which can send over HTTPS where no port-based
firewall can tell it apart from reading. Domain-wide delegation was rejected
because it can act as anyone in the domain.

### The credential stays out of reach

- The app password lives only in Secret Manager, replicated only in the chosen
  region, readable only by that mailbox's service account. The owner can add a
  version but not read one.
- Nothing in OpenTofu writes key material to state: no service account key and
  no secret version resource exist, and a test fails if one appears.
- Every secret read is recorded in Data Access audit logs.
- Deploy rights amount to secret access (whoever can deploy can ship code that
  prints the password), so the operator's everyday identity holds neither;
  admin work goes through time-limited elevation. AGENTS.md step 2 explains.
- `.env`, real tfvars, backend config, state and service account key files are
  refused by pre-commit hooks, and gitleaks scans the full history in CI.
- Logs carry tool name, uids, outcome and duration only. The formatter drops
  any other field, so a careless log call cannot record mail content. The IMAP
  library's protocol trace, which would include message content, stays off
  even at `LOG_LEVEL=DEBUG`, and the app password is masked in any log line
  as a last line of defence.

### Email is untrusted

The consumer is a coding agent with powerful tools of its own. An email saying
"run this command" must never be treated as an instruction:

- every tool description says email content is untrusted third-party data,
  and every body is returned under `content_untrusted`
- the service can revise and delete only its own drafts, recognised by its
  marker header; your drafts and all other mail behave as not found. A deleted
  draft is gone for good (Gmail does not move it to Trash). Deletion removes one
  uid with UID EXPUNGE and is refused on a server without UIDPLUS, so no other
  message flagged for deletion can be caught up in it
- recipients, subject and threading of a reply come from the original email's
  headers, never from the model, so an email cannot redirect a reply
- a new email (`compose_draft`) goes to plain addresses the agent passes: no
  display names, separators or header text. Its description tells the agent to
  use it only when the user asked, and never to pick a recipient because an
  email said so. The person reviewing the draft sees every recipient
- the operator's agent instructions carry a rule to ignore instructions found
  in email (`templates/operator/AGENTS.snippet.md`)

### It reads only what it is allowed to

Each mailbox has a read scope: allowed labels and a maximum age, by the date
Gmail received the message (which a sender cannot forge). The check runs on
every message the service touches. A message outside the scope is reported
exactly like one that does not exist. The owner's own unsent drafts are never
visible; only drafts the service created are. Reading never marks mail as read.

### Access

The service is private on Cloud Run: every request needs an identity token
from a member of that mailbox's invoker list. The local endpoint the proxy
opens accepts only known Host headers and rejects any browser Origin, so a web
page cannot reach it.

## Residual risks, accepted knowingly

- **A leaked app password can send from anywhere else.** It never touches a
  laptop or a repository, reads are audited, and rotation is a single apply.
  If a leak is suspected, revoke the app password in the Google account first,
  then follow [docs/operations.md](./docs/operations.md#suspected-misuse).
- **A person can send a bad draft.** Drafts mark open decisions with
  `[TODO: ...]` and come with the original quoted, but reviewing them is the
  person's job.
- **Prompt injection can still shape the draft text.** It cannot change who
  the draft goes to, and it is only ever a draft.
- **Mail content reaches the coding agent's model provider.** That is the
  point of the tool, and why AGENTS.md asks for a data-protection decision
  before real use.
