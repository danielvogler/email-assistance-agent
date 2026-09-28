"""Turn mail objects into the JSON the MCP tools return.

Message bodies go under `content_untrusted` so every consumer sees, in the
data itself, that the text came from a third party.
"""

from __future__ import annotations

from typing import Any

from email_assistance_agent.mail.draft_edit import DraftContent
from email_assistance_agent.mail.fetch import MessageMeta
from email_assistance_agent.mail.search import ReadMessage, Thread


def header(meta: MessageMeta, name: str) -> str:
    """Return a decoded header value, or an empty string."""
    return str(meta.headers.get(name, "")).strip()


def summary(meta: MessageMeta) -> dict[str, Any]:
    """Headers and metadata of one message, without its body."""
    return {
        "uid": meta.uid,
        "thread_id": str(meta.thread_id) if meta.thread_id is not None else None,
        "from": header(meta, "From"),
        "to": header(meta, "To"),
        "cc": header(meta, "Cc"),
        "subject": header(meta, "Subject"),
        "date": header(meta, "Date"),
        "received": meta.internal_date.isoformat(),
        "labels": list(meta.labels),
    }


def message(read: ReadMessage) -> dict[str, Any]:
    """One message with its body marked as untrusted content."""
    return {
        **summary(read.meta),
        "content_untrusted": read.body.text,
        "truncated": read.body.truncated,
    }


def thread(result: Thread) -> dict[str, Any]:
    """The readable messages of a thread and how many were left out."""
    return {
        "messages": [message(item) for item in result.messages],
        "omitted_out_of_scope": result.omitted_out_of_scope,
        "omitted_over_limit": result.omitted_over_limit,
    }


def draft_summary(meta: MessageMeta) -> dict[str, Any]:
    """A draft this service created."""
    return {
        "uid": meta.uid,
        "to": header(meta, "To"),
        "cc": header(meta, "Cc"),
        "subject": header(meta, "Subject"),
        "in_reply_to": header(meta, "In-Reply-To"),
        "created": meta.internal_date.isoformat(),
    }


def draft(read: DraftContent) -> dict[str, Any]:
    """One of the service's drafts, with the text to pass back to update_draft."""
    return {
        **draft_summary(read.meta),
        "editable_text": read.editable_text,
        "content": read.content,
    }
