"""Create and list agent drafts. Nothing here sends, deletes or expunges."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from email.message import EmailMessage
from typing import Any

from imapclient.imapclient import DRAFT

from email_assistance_agent.mail.fetch import MessageMeta, fetch_meta
from email_assistance_agent.mail.reply import AGENT_MARKER_HEADER, AGENT_MARKER_VALUE

logger = logging.getLogger(__name__)

APPENDUID_PATTERN = re.compile(rb"APPENDUID\s+\d+\s+(\d+)", re.IGNORECASE)
DRAFT_FLAGS = (DRAFT,)


def parse_appenduid(response: object) -> int | None:
    """Extract the new message's uid from an APPEND response (RFC 4315)."""
    raw = response if isinstance(response, bytes) else str(response).encode()
    match = APPENDUID_PATTERN.search(raw)
    return int(match.group(1)) if match else None


def append_draft(client: Any, folder: str, draft: EmailMessage, now: datetime) -> int | None:
    r"""Store `draft` in the Drafts folder with only the \Draft flag.

    Returns:
        The draft's uid, or None if the server did not report one.
    """
    response = client.append(folder, draft.as_bytes(), flags=DRAFT_FLAGS, msg_time=now)
    uid = parse_appenduid(response)
    if uid is None:
        logger.warning("APPEND succeeded but returned no APPENDUID; draft uid unknown")
    return uid


def is_agent_draft(meta: MessageMeta) -> bool:
    """True when the draft carries this service's marker header."""
    return str(meta.headers.get(AGENT_MARKER_HEADER, "")).strip() == AGENT_MARKER_VALUE


def list_drafts(client: Any, folder: str, limit: int) -> list[MessageMeta]:
    """Return the newest drafts this service created, newest first.

    The person's own drafts are never returned, even if the server-side
    header search matched them.
    """
    client.select_folder(folder, readonly=True)
    uids = client.search(["HEADER", AGENT_MARKER_HEADER, AGENT_MARKER_VALUE])
    newest = sorted((int(uid) for uid in uids), reverse=True)[:limit]
    drafts = [meta for meta in fetch_meta(client, newest) if is_agent_draft(meta)]
    return sorted(drafts, key=lambda m: m.internal_date, reverse=True)
