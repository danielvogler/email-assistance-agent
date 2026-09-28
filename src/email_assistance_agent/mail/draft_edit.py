"""Revise and delete drafts, only ever the ones this service created.

A draft without the service's marker header, and anything that is not a
draft, behaves as not found. IMAP cannot change a stored message, so a
revision appends the new version first and removes the old one after: a
failure part-way leaves two drafts, never none.

Removal flags one uid and expunges exactly that uid (UID EXPUNGE, RFC 4315).
A plain EXPUNGE would also remove every other message flagged deleted in the
folder, so without UIDPLUS nothing is deleted at all. On Gmail an expunged
draft is gone for good, not moved to Trash.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from email.message import EmailMessage, Message
from email.utils import getaddresses
from typing import Any

from email_assistance_agent.mail.body import Body
from email_assistance_agent.mail.compose import build_new_draft
from email_assistance_agent.mail.drafts import append_draft, is_agent_draft
from email_assistance_agent.mail.fetch import fetch_full, fetch_meta
from email_assistance_agent.mail.reply import build_reply

UIDPLUS = b"UIDPLUS"


class DraftNotFound(LookupError):
    """Raised for a uid that is not a draft this service created."""

    def __init__(self, uid: int) -> None:
        super().__init__(f"Draft {uid} was not found.")
        self.uid = uid


class DraftError(ValueError):
    """Raised when a draft cannot be revised or deleted safely."""


def addresses(message: Message, header: str) -> list[str]:
    """The bare addresses in one header of a stored draft."""
    return [addr for _, addr in getaddresses([str(v) for v in message.get_all(header, [])]) if addr]


def load_agent_draft(client: Any, folder: str, uid: int) -> Message:
    """Select Drafts for writing and return the draft, if it is one of ours."""
    client.select_folder(folder, readonly=False)
    metas = fetch_meta(client, [uid])
    if not metas or not is_agent_draft(metas[0]):
        raise DraftNotFound(uid)
    full = fetch_full(client, uid)
    if full is None:
        raise DraftNotFound(uid)
    return full


def delete_draft(client: Any, folder: str, uid: int) -> None:
    """Permanently remove one of this service's drafts, and nothing else."""
    load_agent_draft(client, folder, uid)
    if UIDPLUS not in client.capabilities():
        raise DraftError("The mail server cannot delete a single message safely (no UIDPLUS).")
    client.delete_messages([uid])
    client.uid_expunge([uid])


def revised_new_email(
    old: Message, body: str, subject: str | None, *, own_address: str, signature: str | None
) -> EmailMessage:
    """A new version of a compose_draft draft: same recipients, new text."""
    return build_new_draft(
        addresses(old, "To"),
        subject if subject is not None else str(old.get("Subject", "")),
        body,
        own_address=own_address,
        cc=addresses(old, "Cc"),
        signature=signature,
    )


def revised_reply(
    old: Message,
    original: Message,
    original_body: Body,
    body: str,
    *,
    own_address: str,
    signature: str | None,
) -> EmailMessage:
    """A new version of a reply draft: rebuilt from the original, same recipients."""
    draft = build_reply(original, original_body, body, own_address=own_address, signature=signature)
    for header in ("To", "Cc"):
        del draft[header]
        values: Sequence[str] = [str(v) for v in old.get_all(header, [])]
        if values:
            draft[header] = ", ".join(values)
    return draft


def replace_draft(client: Any, folder: str, old_uid: int, new: EmailMessage, now: datetime) -> int | None:
    """Store the new version, then remove the old one."""
    new_uid = append_draft(client, folder, new, now)
    delete_draft(client, folder, old_uid)
    return new_uid
