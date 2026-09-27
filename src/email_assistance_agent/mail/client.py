"""IMAP connection handling and special-use folder lookup."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from imapclient import IMAPClient
from imapclient.imapclient import ALL, DRAFTS

from email_assistance_agent.config import Settings

logger = logging.getLogger(__name__)

# Used only when the server does not advertise RFC 6154 special-use flags.
# The names are locale-dependent in Gmail, which is why lookup comes first.
FALLBACK_ALL_MAIL = "[Gmail]/All Mail"
FALLBACK_DRAFTS = "[Gmail]/Drafts"


def connect(settings: Settings) -> Any:
    """Open an authenticated SSL connection. The caller must log out."""
    client = IMAPClient(
        settings.imap_host,
        port=settings.imap_port,
        ssl=True,
        timeout=settings.imap_timeout_seconds,
    )
    # Keep INTERNALDATE timezone-aware so age checks do not depend on the
    # container's local zone.
    client.normalise_times = False
    client.login(settings.email_user, settings.email_password.get_secret_value())
    return client


@contextmanager
def session(settings: Settings) -> Iterator[Any]:
    """Yield one connection for one tool call and always log out.

    There is no pooling on purpose: Gmail allows about 15 concurrent IMAP
    connections per account, and the service scales to zero between calls.
    """
    client = connect(settings)
    try:
        yield client
    finally:
        try:
            client.logout()
        except Exception:  # the call's own error, if any, matters more
            logger.warning("IMAP logout failed", exc_info=True)


def find_folder(client: Any, flag: bytes, fallback: str) -> str:
    """Return the folder carrying a special-use flag, or the fallback name."""
    folder = client.find_special_folder(flag)
    return str(folder) if folder else fallback


def all_mail_folder(client: Any) -> str:
    """Return Gmail's All Mail folder in whatever language the account uses."""
    return find_folder(client, ALL, FALLBACK_ALL_MAIL)


def drafts_folder(client: Any, settings: Settings) -> str:
    """Return the Drafts folder, preferring the special-use flag over config."""
    return find_folder(client, DRAFTS, settings.drafts_folder or FALLBACK_DRAFTS)
