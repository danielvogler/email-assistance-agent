"""Build a threaded reply draft from an original message.

Everything that decides where a draft goes (To, Cc, Subject, threading) is
derived from the original's headers. The model only supplies the reply text,
so neither it nor an injected email can choose a recipient.
"""

from __future__ import annotations

from collections.abc import Iterable
from email.message import EmailMessage, Message
from email.utils import formataddr, formatdate, getaddresses, make_msgid

from email_assistance_agent.mail.body import Body

AGENT_MARKER_HEADER = "X-Drafted-By"
AGENT_MARKER_VALUE = "email-assistance-agent"
REPLY_PREFIX = "Re: "
SIGNATURE_DELIMITER = "-- "
QUOTE_PREFIX = "> "
TRUNCATION_MARKER = "[...]"


class ReplyError(ValueError):
    """Raised when the original lacks the headers a reply needs."""


Address = tuple[str, str]


def parse_addresses(msg: Message, *header_names: str) -> list[Address]:
    """Parse every address in the named headers, skipping empty entries."""
    values = [str(value) for name in header_names for value in msg.get_all(name, [])]
    return [(name, addr) for name, addr in getaddresses(values) if addr and "@" in addr]


def dedupe(addresses: Iterable[Address], exclude: Iterable[str]) -> list[Address]:
    """Drop duplicates and excluded addresses, comparing case-insensitively."""
    seen = {addr.casefold() for addr in exclude}
    result: list[Address] = []
    for name, addr in addresses:
        key = addr.casefold()
        if key not in seen:
            seen.add(key)
            result.append((name, addr))
    return result


def reply_subject(original_subject: str) -> str:
    """Prefix Re: once, whatever case an existing prefix uses."""
    subject = original_subject.strip()
    if subject.casefold().startswith("re:"):
        return subject
    return REPLY_PREFIX + subject


def quote(original: Message, original_body: Body) -> str:
    """Render the original as an attributed plain-text quote."""
    sender = str(original.get("From", "")).strip() or "the sender"
    date = str(original.get("Date", "")).strip()
    attribution = f"On {date}, {sender} wrote:" if date else f"{sender} wrote:"
    lines = original_body.text.splitlines() or [""]
    if original_body.truncated:
        lines = [*lines, TRUNCATION_MARKER]
    quoted = "\n".join((QUOTE_PREFIX + line).rstrip() for line in lines)
    return f"{attribution}\n{quoted}"


def compose_text(body: str, signature: str | None, original: Message, original_body: Body) -> str:
    """Lay out reply text, then signature, then the quoted original."""
    sections = [body.strip()]
    if signature and signature.strip():
        sections.append(f"{SIGNATURE_DELIMITER}\n{signature.strip()}")
    sections.append(quote(original, original_body))
    return "\n\n".join(sections) + "\n"


def build_reply(
    original: Message,
    original_body: Body,
    body: str,
    *,
    own_address: str,
    reply_all: bool = False,
    signature: str | None = None,
) -> EmailMessage:
    """Return a new draft replying to `original`. Pure: no I/O, no mutation.

    Raises:
        ReplyError: If the original has no usable sender or Message-ID.
    """
    message_id = str(original.get("Message-ID", "")).strip()
    if not message_id:
        raise ReplyError("The original message has no Message-ID, so a reply cannot be threaded.")
    recipients = parse_addresses(original, "Reply-To") or parse_addresses(original, "From")
    if not recipients:
        raise ReplyError("The original message has no usable sender address.")

    to = dedupe(recipients, exclude=[own_address])
    if not to:
        raise ReplyError("The original message was sent by this mailbox; there is no one to reply to.")
    cc = dedupe(parse_addresses(original, "To", "Cc"), exclude=[own_address, *(a for _, a in to)])

    draft = EmailMessage()
    draft["From"] = own_address
    draft["To"] = ", ".join(formataddr(addr) for addr in to)
    if reply_all and cc:
        draft["Cc"] = ", ".join(formataddr(addr) for addr in cc)
    draft["Subject"] = reply_subject(str(original.get("Subject", "")))
    draft["Date"] = formatdate(localtime=True)
    draft["Message-ID"] = make_msgid(domain=own_address.rsplit("@", 1)[1])
    draft["In-Reply-To"] = message_id
    draft["References"] = " ".join(filter(None, [str(original.get("References", "")).strip(), message_id]))
    draft[AGENT_MARKER_HEADER] = AGENT_MARKER_VALUE
    draft.set_content(compose_text(body, signature, original, original_body))
    return draft
