"""Search and read messages in All Mail, limited to the read scope.

An out-of-scope message is reported exactly like a missing one, so an error
never reveals that a message exists outside what the server may read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.message import Message
from typing import Any

from email_assistance_agent.mail.body import Body, extract_body
from email_assistance_agent.mail.client import all_mail_folder
from email_assistance_agent.mail.drafts import is_agent_draft
from email_assistance_agent.mail.fetch import MessageMeta, fetch_full, fetch_meta
from email_assistance_agent.mail.scope import ReadScope, gmail_filter, in_scope

SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 50
MAX_THREAD_MESSAGES = 30


class MessageNotFound(LookupError):
    """Raised for a uid that does not exist or is outside the read scope."""

    def __init__(self, uid: int) -> None:
        super().__init__(f"Message {uid} was not found.")
        self.uid = uid


@dataclass(frozen=True)
class ReadMessage:
    """One readable message: metadata plus its extracted body."""

    meta: MessageMeta
    body: Body
    raw_headers: Message


@dataclass(frozen=True)
class Thread:
    """The readable part of a Gmail thread, oldest first."""

    messages: tuple[ReadMessage, ...]
    omitted_out_of_scope: int
    omitted_over_limit: int


def clamp_limit(limit: int) -> int:
    """Keep a caller's limit within 1..SEARCH_LIMIT_MAX."""
    return max(1, min(limit, SEARCH_LIMIT_MAX))


class EmptyQuery(ValueError):
    """Raised for a blank search query."""


def scoped_query(query: str, scope: ReadScope, now: datetime) -> str:
    """Combine the caller's Gmail query with the scope filter.

    Raises:
        EmptyQuery: If the query is blank.
    """
    if not query.strip():
        raise EmptyQuery("A search query is required.")
    prefix = gmail_filter(scope, now)
    # The spaces inside the parentheses are load-bearing: IMAPClient quotes a
    # search string only when it contains a space, and an unquoted "(x)" is
    # not a valid IMAP atom, so Gmail rejects the command.
    return f"{prefix} ( {query.strip()} )".strip()


DRAFT_LABEL = "\\Draft"


def is_private_draft(meta: MessageMeta) -> bool:
    """A draft the mailbox owner is writing; only the service's own drafts are visible."""
    return DRAFT_LABEL in meta.labels and not is_agent_draft(meta)


def readable(metas: list[MessageMeta], scope: ReadScope, now: datetime) -> list[MessageMeta]:
    """Keep only the messages the scope allows, never the owner's unsent drafts."""
    return [m for m in metas if in_scope(m.labels, m.internal_date, scope, now) and not is_private_draft(m)]


def search(client: Any, scope: ReadScope, query: str, limit: int, now: datetime) -> list[MessageMeta]:
    """Run a Gmail search and return the newest in-scope matches."""
    client.select_folder(all_mail_folder(client), readonly=True)
    uids = client.gmail_search(scoped_query(query, scope, now))
    # Fetch a little more than asked, since some matches may be dropped.
    candidates = sorted((int(uid) for uid in uids), reverse=True)[: clamp_limit(limit) * 2]
    metas = readable(fetch_meta(client, candidates), scope, now)
    return sorted(metas, key=lambda m: m.internal_date, reverse=True)[: clamp_limit(limit)]


def load_meta(client: Any, scope: ReadScope, uid: int, now: datetime) -> MessageMeta:
    """Return one message's metadata, or raise if missing or out of scope."""
    metas = readable(fetch_meta(client, [uid]), scope, now)
    if not metas:
        raise MessageNotFound(uid)
    return metas[0]


def load_message(client: Any, meta: MessageMeta) -> ReadMessage:
    """Fetch the full message for metadata that already passed the scope check."""
    full = fetch_full(client, meta.uid)
    if full is None:
        raise MessageNotFound(meta.uid)
    return ReadMessage(meta=meta, body=extract_body(full), raw_headers=full)


def read_message(client: Any, scope: ReadScope, uid: int, now: datetime) -> ReadMessage:
    """Read one in-scope message from All Mail."""
    client.select_folder(all_mail_folder(client), readonly=True)
    return load_message(client, load_meta(client, scope, uid, now))


def read_thread(client: Any, scope: ReadScope, uid: int, now: datetime) -> Thread:
    """Read the in-scope messages of the thread containing `uid`."""
    client.select_folder(all_mail_folder(client), readonly=True)
    anchor = load_meta(client, scope, uid, now)
    if anchor.thread_id is None:
        return Thread(messages=(load_message(client, anchor),), omitted_out_of_scope=0, omitted_over_limit=0)
    thread_uids = [int(u) for u in client.search(["X-GM-THRID", anchor.thread_id])]
    metas = fetch_meta(client, thread_uids)
    allowed = sorted(readable(metas, scope, now), key=lambda m: m.internal_date)
    kept = allowed[-MAX_THREAD_MESSAGES:]
    return Thread(
        messages=tuple(load_message(client, meta) for meta in kept),
        omitted_out_of_scope=len(metas) - len(allowed),
        omitted_over_limit=len(allowed) - len(kept),
    )
