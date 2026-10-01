# AGENTS.md

This file is the single source of instructions for any coding agent working
with this repository (CLAUDE.md and GEMINI.md only point here). Two readers
arrive, so it has two parts:

- **[A. Using this](#a-using-this)**: setting it up for somebody's mailbox,
  connecting to it and keeping it running.
- **[B. Changing the code](#b-changing-the-code)**: layout, checks,
  conventions, and what will bite you.

## What this is

An email assistant for coding agents: an [MCP](https://modelcontextprotocol.io)
server that gives an agent one or more Gmail / Google Workspace mailboxes. The
agent can search, read messages and whole conversations, and prepare replies,
which land in Gmail as drafts in the original conversation. A person reviews
and sends them. The service itself has no way to send, and the deployment
enforces that:

1. It signs in with a Gmail **app password**, which works over IMAP and SMTP
   but not the Gmail REST API. (Every OAuth scope that can create drafts can
   also send, so OAuth is deliberately not used.)
2. On Cloud Run, all egress goes through a VPC whose firewall **denies tcp 465
   and 587**. Google Cloud already blocks 25. With SMTP closed and no REST
   access, the credential has no route that sends.
3. The app password lives in **Secret Manager**, readable only by the
   service's own identity. The mailbox owner can add a version, not read one.
4. **Replies cannot be redirected.** `create_draft` takes the uid being
   answered and the reply text; To, Cc, Subject and threading are derived from
   the original. `compose_draft` writes a new email to plain addresses the agent
   passes, for when the user asks for one; its description forbids choosing a
   recipient because an email said so. Either way a person sees the recipients
   before sending.

Invariants that every change must keep:

- never send; delete or replace only the service's own drafts (marker header,
  one uid, UID EXPUNGE); never set `\Seen` (reads use
  `BODY.PEEK` on read-only selected folders)
- email content is **untrusted third-party data**: bodies are returned as
  `content_untrusted`, and every tool description says so
- logs carry tool name, uids, outcome and duration only; never bodies,
  subjects, addresses or credentials
- no company-specific values in this repository; it is public

[SECURITY.md](./SECURITY.md) has the full threat model.

---

## A. Using this

The operator keeps **their own private repository** (for example a company ops
repo) for the values: which project, which mailboxes, where state lives, and
the dated verification record. This repository provides everything else and
is used at a pinned commit.

Work through the steps in order. Each ends with how to know it worked. Do not
skip step 6: the service is not ready for real mail until every check passes.

### 1. Prerequisites

Check each tool and version before starting:

| Tool | Check | Needed for |
|---|---|---|
| uv | `uv --version` (0.9+) | running the code and tests |
| OpenTofu | `tofu version` (1.8+) | the infrastructure (not Terraform) |
| gcloud | `gcloud --version` | builds, secrets, the proxy |
| git | `git --version` | pinning this repository |
| Claude Code, or any MCP client with HTTP transport | `claude --version` | using the service |

Docker is optional (only for `make docker-smoke`); images are built with
Cloud Build.

Accounts and access:

- a **Google Workspace or Gmail mailbox** with 2-Step Verification on, where
  the Workspace admin allows **app passwords** and **IMAP**
- a **GCP billing account** you can link to a new project
- an **admin identity** that can create projects, and a separate **everyday
  identity** (the one your coding agent runs as); see step 2.5
- `gcloud auth login` and `gcloud auth application-default login` done

A GCS bucket for OpenTofu state is created in step 4 unless you already have
one to reuse.

**Done when:** every check prints a version and `gcloud auth list` shows your
account.

### 2. Decisions to record

Ask the mailbox owner and write the answers into the operator repository
before creating anything:

1. **Which mailboxes**, each with a short key (`alex`), its address, who owns
   it, and who may call it.
2. **What each may read:** `read_labels` (for example `["INBOX", "SENT"]`
   for both sides of every conversation; system labels are `INBOX`, `SENT`,
   `STARRED`, `IMPORTANT`, anything else is a user label; empty means
   everything) and `read_max_age_days` (empty means no limit).
3. **A dedicated GCP project.** Not a shared one: whoever holds Owner in the
   project can read every mailbox secret, which defeats the isolation.
4. **Region**, chosen for data residency. The default is `europe-west6`.
5. **How admin work is done without everyday admin rights.** Anyone who can
   deploy a revision can ship code that prints the password, so deploy rights
   are secret access. Recommended: a Privileged Access Manager entitlement
   (time-bound, e.g. 1h, justification logged) granting Owner for applies.
   Alternative: a separate admin account. The everyday identity keeps only
   `roles/viewer`, `roles/run.invoker` (granted by this module) and
   `roles/secretmanager.secretVersionAdder` on its own secret.
6. **Data protection.** Searching the mailbox sends email content to the
   coding agent's model provider. Get whoever is responsible for data
   protection to agree and record it. This gates real use.
7. **A test mailbox** (a throwaway Gmail) for trying things out. Never develop
   or experiment against a real mailbox.

**Done when:** `DECISIONS.md` (copied in step 3) has an answer for all seven.

### 3. Copy the templates

```bash
git clone https://github.com/danielvogler/email-assistance-agent
cd email-assistance-agent
git checkout <tag or commit>        # pin it; record it in the operator repo
mkdir -p <operator-repo>/infra/email-assistance-agent
cp templates/operator/email-assistance-agent.tfvars.example <operator-repo>/infra/email-assistance-agent/email-assistance-agent.tfvars
cp templates/operator/backend.hcl.example         <operator-repo>/infra/email-assistance-agent/backend.hcl
cp templates/operator/VERIFICATION.md             <operator-repo>/infra/email-assistance-agent/VERIFICATION.md
cp templates/operator/DECISIONS.md                <operator-repo>/infra/email-assistance-agent/DECISIONS.md
```

Record the step 2 answers in `DECISIONS.md`, then fill in the tfvars and the
backend config from them. If you change `name_prefix` from its default, pass
the same value as `PREFIX=` to every `make` deployment target. Leave `image = null` and every
`secret_version` unset for now. `AGENTS.snippet.md` is used in step 7.

**Done when:** `DECISIONS.md`, `email-assistance-agent.tfvars` and
`backend.hcl` contain real values and no `REPLACE` placeholder remains.

### 4. Bootstrap the project and the first apply

As the **admin identity**, create and link the project (skip if it exists).
Whoever creates a project becomes its Owner, which is why this is not the
everyday identity:

```bash
gcloud projects create <PROJECT> --set-as-default=false
gcloud billing projects link <PROJECT> --billing-account <BILLING_ACCOUNT>
gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com \
  storage.googleapis.com --project <PROJECT>
```

Create the state bucket, unless you reuse one (then make sure the everyday
identity cannot write it):

```bash
gcloud storage buckets create gs://<STATE_BUCKET> --project <PROJECT> --location <REGION> \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://<STATE_BUCKET> --versioning --project <PROJECT>
```

Give the everyday identity read access only, and make sure it holds no Owner
or Editor role in the project:

```bash
gcloud projects add-iam-policy-binding <PROJECT> --member user:<EVERYDAY> --role roles/viewer
gcloud projects get-iam-policy <PROJECT> --flatten=bindings --filter="bindings.members:user:<EVERYDAY>" \
  --format="value(bindings.role)"          # expect roles/viewer only
```

If you use Privileged Access Manager for admin work, set up the entitlement
now, following Google's documentation for Privileged Access Manager
(time-bound Owner on this project, justification required).

Then, as the admin identity (or elevated through the entitlement):

```bash
make infra-init  BACKEND=<operator-repo>/infra/email-assistance-agent/backend.hcl
make infra-plan  TFVARS=<operator-repo>/infra/email-assistance-agent/email-assistance-agent.tfvars
make infra-apply TFVARS=<operator-repo>/infra/email-assistance-agent/email-assistance-agent.tfvars
```

Read the plan before applying it. This first apply creates the APIs, network,
firewall, NAT, registry, audit logging, service accounts and empty secrets.
No service exists yet.

**Done when:** the apply succeeds and `tofu -chdir=infra output
pending_mailboxes` lists every mailbox.

### 5. Build the image, add the passwords, second apply

```bash
make image PROJECT=<PROJECT> REGION=<REGION>
```

It prints a line `image = "…@sha256:…"`. Put it in `email-assistance-agent.tfvars`.

For each mailbox, the **owner** creates an app password in their Google account
(Security → 2-Step Verification → App passwords) and pipes it straight into
Secret Manager. Never write it to a file, a chat or a terminal log:

```bash
read -rs APP_PASSWORD                       # paste it; nothing is echoed or logged
printf '%s' "$APP_PASSWORD" | gcloud secrets versions add email-agent-<key>-app-password \
  --data-file=- --project <PROJECT>
unset APP_PASSWORD
```

The command prints the version number. Set it as that mailbox's
`secret_version` (a number, never `latest`). Then plan and apply again, as in
step 4.

**Done when:** `pending_mailboxes` is empty and `tofu -chdir=infra output
services` shows a URL and proxy command per mailbox.

### 6. Verify, before any real use

Fill in `VERIFICATION.md` in the operator repository as you go. Every line
must pass:

1. `make verify PROJECT=<PROJECT> REGION=<REGION>` succeeds: SMTP ports are
   BLOCKED and IMAP is OPEN from the service network.
2. With the proxy running (step 7), the MCP tool list is exactly
   `search`, `read_message`, `read_thread`, `list_drafts`, `read_draft`,
   `create_draft`, `compose_draft`, `update_draft`, `delete_draft`.
3. `create_draft` on a message in the mailbox: the draft appears in Gmail
   inside the original conversation, To/Cc/Subject are right, and the original
   is still unread if it was unread.
4. As the everyday identity, reading the secret fails with
   `PERMISSION_DENIED`:
   `gcloud secrets versions access latest --secret email-agent-<key>-app-password --project <PROJECT>`
5. As the everyday identity, deploying fails with `PERMISSION_DENIED`:
   `gcloud run deploy email-agent-<key> --image <IMAGE> --region <REGION> --project <PROJECT>`
6. Cloud Logging shows a Secret Manager data-access entry for the service
   account when an instance starts.
7. The data-protection decision from step 2.6 is linked.

**Done when:** every line in `VERIFICATION.md` is marked passed, with a date.

### 7. Connect

Start the proxy (it signs requests with your Google identity), register the
server with your MCP client, and harden the client:

```bash
make proxy PROJECT=<PROJECT> REGION=<REGION> MAILBOX=<key>     # leave running
claude mcp add --transport http --scope user email-assistance-agent http://localhost:8080/mcp
```

In the client's settings (for Claude Code, `~/.claude/settings.json`, not a
repository), deny the agent the routes around the design. Check the current
permission-rule syntax in your client's documentation:

```json
{ "permissions": { "deny": ["Bash(gcloud secrets:*)", "Read(**/.env)"] } }
```

Paste `templates/operator/AGENTS.snippet.md` into the operator repository's
agent instructions and fill in its placeholders. It tells every future agent
session what the tool reads, what it writes, and that email is untrusted.

**Done when:** in a new agent session, the nine tools are listed and a
`search` returns results.

### 8. Day two

Full procedures are in [docs/operations.md](./docs/operations.md):

- **Upgrade:** check out a newer tag, `make image`, update `image`, plan, apply.
- **Rotate a password:** add a new version, bump `secret_version`, apply,
  revoke the old app password, disable the old version (admin rights).
- **Add a mailbox:** one `mailboxes` entry, apply, add its password, set its
  version, apply, verify.
- **Offboard someone:** remove them from `invoker_members`, apply; if it is
  their mailbox, revoke the app password, remove the entry and set
  `deletion_protection = false` for that one apply, then back to true.
- **Suspected misuse:** revoke the app password first, then investigate.

### What never goes into git

In either repository: `.env`, app passwords, OpenTofu state, and per-draft
logs or summaries (subjects carry client and personal detail; the Gmail Drafts
folder is the log). In this public repository additionally: any real project
id, mailbox address, bucket name or tfvars file. Pre-commit hooks reject most
of these; do not work around them.

---

## B. Changing the code

### Layout

```
src/email_assistance_agent/
  config.py          Settings from env / .env, validated at startup
  server.py          the MCP server: nine tools, envelope, validation, main()
  presenters.py      JSON shapes the tools return
  logging_setup.py   JSON logs with an allowlist of fields
  egress_check.py    the SMTP-blocked probe run as a Cloud Run job
  mail/
    client.py        connection per call, special-use folder lookup
    fetch.py         BODY.PEEK fetches of metadata and bodies
    scope.py         label and age limits (the per-message check enforces)
    search.py        search, read_message, read_thread
    reply.py         build_reply: recipients, threading, quote, signature
    compose.py       build_new_draft: a new email to plain addresses
    draft_edit.py    read, update and delete, only for the service's own drafts
    drafts.py        append_draft, list_drafts
tests/               unit, integration (tools in process, HTTP), guard
infra/               OpenTofu root module, no values; tests with a mocked provider
templates/operator/  files an operator copies into their private repository
```

### Commands

```bash
make setup          # uv sync + git hooks
make run            # serve MCP at http://localhost:8080/mcp (needs .env)
make check          # lint, format check, mypy strict, pytest, tofu validate + test
make format         # fix formatting
make docker-smoke   # build the image and check its tool list (needs Docker)
```

`make check` is exactly what CI runs. Coverage must stay at or above 80%.
For local runs, copy `.env.example` to `.env` and use a **test mailbox**.

### Adding or changing a tool

1. Add it to `server.py` with an explicit description that ends with
   `UNTRUSTED_NOTICE`, typed and constrained arguments, and the right
   `ToolAnnotations`.
2. Add its name to `ALLOWED_TOOLS`. The allowlist test fails otherwise, and it
   also fails for any name containing send, delete, move, expunge, trash or
   flag. Such a tool must not exist.
3. Return data through `presenters.py`, with any body under
   `content_untrusted`.
4. Route every mail read through the read scope (`load_meta` / `readable`).
   Out-of-scope must look exactly like not found.
5. Log through `run_tool` only. Add a field to `ALLOWED_EXTRA_FIELDS` only if
   it can never carry mail content.

### Conventions

- Python 3.12+, uv, ruff (line length 110, Google docstrings), mypy strict.
- Frozen dataclasses and pure functions for mail logic; I/O stays in
  `client.py`, `fetch.py`, `search.py` and `drafts.py`.
- Tests first; the IMAP fake in `tests/fakes.py` has no methods that change
  flags or delete, so code that tries fails.
- Commits: conventional with a scope (`fix(mail): …`), imperative subject
  under 72 characters, bullets saying why. No AI co-author trailers; the
  commit-msg hook rejects them.
- Infrastructure: OpenTofu, `tofu fmt`; never add a
  `google_service_account_key` or `google_secret_manager_secret_version`
  resource (a guard test fails), and never grant `allUsers`.

### Things that will bite you

- **IMAPClient quotes a search string only if it contains a space.** An
  unquoted `(x)` is not a valid IMAP atom and Gmail rejects the whole command.
  `scoped_query` pads its parentheses for this; keep it that way.
- **`INTERNALDATE` is naive local time unless `normalise_times` is off.**
  `connect()` turns it off so age checks do not depend on the container's zone.
- **Gmail reports the inbox as `\Inbox` in `X-GM-LABELS` but searches it as
  `in:inbox`.** `scope.py` maps the configured name `INBOX` to both.
- **Drafts show up in All Mail searches** (label `\Draft`). Replying to one
  fails with a clear error, because its sender is the mailbox itself.
- **Folder names are localised** (`[Gmail]/Entwürfe`). Always go through
  `find_special_folder`, never a hardcoded name.
- **Gmail throttles rapid logins.** Every tool call opens its own connection,
  so a burst of calls can fail transiently; the log's `detail` field shows the
  server's reason.
- **MCP SDK v2 renamed FastMCP to `MCPServer`**, and in-process `call_tool`
  raises `ToolError` for invalid arguments instead of returning `is_error`.
- **The mocked OpenTofu provider invents values** for computed attributes, so
  two resources can share a made-up email. Assert on inputs such as
  `account_id`, not on computed outputs.
- **The live suite does not exist in CI.** Anything touching Gmail's real
  response shapes needs a manual run against a test mailbox (`make run` and an
  MCP client), and the result belongs in the pull request description.

- **Draft uids are not message uids.** `list_drafts` and the draft tools use
  uids in the Drafts folder; `read_message` looks in All Mail. Read a draft with
  `read_draft`, and pass its `editable_text` to `update_draft`, which re-adds the
  signature and quote.
- **`gcloud run services proxy` sends the legacy host** `<service>-<hash>-<region>.a.run.app`,
  not the deterministic one. The hash only exists after creation, so
  `ALLOWED_HOSTS` allows it by pattern (`http_guard.py`); the Origin check is
  what keeps browsers out. A `*` there matches letters and digits only, so the
  pattern is `<service>-*-*.a.run.app`, and one mailbox's pattern never matches
  another's host.

### Definition of done

- `make check` passes: lint, format, mypy strict, pytest with at least 80%
  coverage, and the OpenTofu validate and tests.
- New behaviour has tests written first; mail logic is tested against
  `tests/fakes.py`, tools through `server.call_tool`.
- The invariants above still hold, and the tool allowlist test still passes
  unchanged unless the tool set was meant to change.
- A change to IMAP behaviour was also run against a test mailbox.
- README, AGENTS.md and SECURITY.md still describe what the code does.
- Commits follow the conventions above and the hooks passed without
  `--no-verify`.
