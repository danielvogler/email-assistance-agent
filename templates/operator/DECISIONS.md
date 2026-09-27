# email-assistance-agent: decisions

Answer every question before creating anything (AGENTS.md, step 2). Keep this
file in the operator repository next to the tfvars; it is the record of why
the deployment looks the way it does.

| # | Decision | Answer | Decided by | Date |
|---|---|---|---|---|
| 1 | Mailboxes: key, address, owner, who may call it | REPLACE | | |
| 2 | Read scope per mailbox: labels, maximum age in days | REPLACE | | |
| 3 | Dedicated GCP project id | REPLACE | | |
| 4 | Region, and the data-residency reason for it | REPLACE | | |
| 5 | How admin work is done (PAM entitlement or separate admin account); the everyday identity | REPLACE | | |
| 6 | Data protection: who agreed that email content may reach the coding agent's model provider, and where it is recorded | REPLACE | | |
| 7 | Test mailbox used for trying things out | REPLACE | | |

State bucket: `REPLACE` (project `REPLACE`). Repository commit deployed: `REPLACE`.
