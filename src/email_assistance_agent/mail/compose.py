"""Build a new draft, not a reply, to recipients the caller names.

Unlike a reply, a new email has no original to take its recipients from, so
the agent supplies them. What keeps this safe is that the result is only ever
a draft: a person reviews the recipients before anything is sent.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from email_assistance_agent.mail.reply import AGENT_MARKER_HEADER, AGENT_MARKER_VALUE, SIGNATURE_DELIMITER

MAX_RECIPIENTS = 20
# Plain addresses only: no display names, quotes, angle brackets or separators,
# so a recipient can never smuggle a second address or a header into the draft.
PLAIN_ADDRESS_PATTERN = r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$"
MAX_SUBJECT_CHARS = 250


class ComposeError(ValueError):
    """Raised when recipients or subject cannot form a valid draft."""


def normalise_recipients(addresses: Sequence[str]) -> list[str]:
    """Strip, validate and deduplicate bare addresses, keeping their order."""
    pattern = re.compile(PLAIN_ADDRESS_PATTERN)
    seen: set[str] = set()
    result: list[str] = []
    for raw in addresses:
        address = raw.strip()
        if not pattern.fullmatch(address):
            raise ComposeError(f"Not a plain email address: {address!r}")
        if address.casefold() not in seen:
            seen.add(address.casefold())
            result.append(address)
    return result


def build_new_draft(
    to: Sequence[str],
    subject: str,
    body: str,
    *,
    own_address: str,
    cc: Sequence[str] = (),
    signature: str | None = None,
) -> EmailMessage:
    """Return a new, unthreaded draft. Pure: no I/O, no mutation.

    Raises:
        ComposeError: If there is no recipient, too many, or an invalid one.
    """
    recipients = normalise_recipients(to)
    copies = [a for a in normalise_recipients(cc) if a.casefold() not in {r.casefold() for r in recipients}]
    if not recipients:
        raise ComposeError("A new draft needs at least one recipient.")
    if len(recipients) + len(copies) > MAX_RECIPIENTS:
        raise ComposeError(f"At most {MAX_RECIPIENTS} recipients in total.")
    if "\n" in subject or "\r" in subject or len(subject) > MAX_SUBJECT_CHARS:
        raise ComposeError(f"The subject must be one line of at most {MAX_SUBJECT_CHARS} characters.")

    draft = EmailMessage()
    draft["From"] = own_address
    draft["To"] = ", ".join(recipients)
    if copies:
        draft["Cc"] = ", ".join(copies)
    draft["Subject"] = subject.strip()
    draft["Date"] = formatdate(localtime=True)
    draft["Message-ID"] = make_msgid(domain=own_address.rsplit("@", 1)[1])
    draft[AGENT_MARKER_HEADER] = AGENT_MARKER_VALUE
    text = body.strip()
    if signature and signature.strip():
        text = f"{text}\n\n{SIGNATURE_DELIMITER}\n{signature.strip()}"
    draft.set_content(text + "\n")
    return draft
