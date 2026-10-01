"""Fetch message metadata and bodies without changing any flags.

Every fetch uses BODY.PEEK, so reading never marks a message as seen. Folders
are selected read-only, except Drafts when the service revises or deletes its
own drafts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from typing import Any

HEADER_FIELDS = "MESSAGE-ID REFERENCES IN-REPLY-TO REPLY-TO FROM TO CC SUBJECT DATE X-DRAFTED-BY"
HEADERS_ITEM = f"BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})]"
FULL_ITEM = "BODY.PEEK[]"
META_ITEMS = ("X-GM-LABELS", "INTERNALDATE", "X-GM-THRID", HEADERS_ITEM)

LABELS_KEY = b"X-GM-LABELS"
DATE_KEY = b"INTERNALDATE"
THREAD_KEY = b"X-GM-THRID"
FULL_KEY = b"BODY[]"


@dataclass(frozen=True)
class MessageMeta:
    """Headers and Gmail metadata for one message, without its body."""

    uid: int
    thread_id: int | None
    labels: tuple[str, ...]
    internal_date: datetime
    headers: Message


def parse_message(raw: bytes) -> Message:
    """Parse raw RFC 5322 bytes with modern header decoding."""
    return BytesParser(policy=policy.default).parsebytes(raw)


def header_bytes(data: Mapping[bytes, Any]) -> bytes:
    """Find the HEADER.FIELDS item, whose exact key spelling varies by server."""
    for key, value in data.items():
        if key.startswith(b"BODY[HEADER") and isinstance(value, bytes):
            return value
    return b""


def decode_labels(raw: Iterable[str | bytes] | None) -> tuple[str, ...]:
    """Normalise X-GM-LABELS entries to text."""
    return tuple(
        label.decode("utf-8", errors="replace") if isinstance(label, bytes) else str(label)
        for label in raw or ()
    )


def fetch_meta(client: Any, uids: Iterable[int]) -> list[MessageMeta]:
    """Fetch labels, INTERNALDATE, thread id and headers for the given uids."""
    wanted = list(uids)
    if not wanted:
        return []
    response = client.fetch(wanted, list(META_ITEMS))
    return [
        MessageMeta(
            uid=int(uid),
            thread_id=int(data[THREAD_KEY]) if data.get(THREAD_KEY) is not None else None,
            labels=decode_labels(data.get(LABELS_KEY)),
            internal_date=data[DATE_KEY],
            headers=parse_message(header_bytes(data)),
        )
        for uid, data in response.items()
        if DATE_KEY in data
    ]


def fetch_full(client: Any, uid: int) -> Message | None:
    """Fetch and parse one complete message, or None if it does not exist."""
    response = client.fetch([uid], [FULL_ITEM])
    raw = response.get(uid, {}).get(FULL_KEY)
    return parse_message(raw) if isinstance(raw, bytes) else None
