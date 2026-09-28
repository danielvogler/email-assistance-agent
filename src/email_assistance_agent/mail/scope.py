"""Which messages the server may read: allowed labels and a maximum age.

The per-message check in `in_scope` is the enforcement. `gmail_filter` only
narrows the server-side search so fewer messages are fetched and dropped.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from email_assistance_agent.config import Settings

# Gmail's system labels, by the name an operator configures: how X-GM-LABELS
# reports each one, and how Gmail search spells it. Any other name is a user
# label, reported and searched by its own name.
SYSTEM_LABELS: dict[str, tuple[str, str]] = {
    "inbox": ("\\Inbox", "in:inbox"),
    "sent": ("\\Sent", "in:sent"),
    "starred": ("\\Starred", "is:starred"),
    "important": ("\\Important", "is:important"),
}
SEARCH_TERMS = dict(SYSTEM_LABELS.values())
FORBIDDEN_LABEL_CHARS = frozenset('"\\()')


class ScopeError(ValueError):
    """Raised when a configured label cannot be expressed safely."""


@dataclass(frozen=True)
class ReadScope:
    """The labels and age a message must satisfy to be readable."""

    labels: frozenset[str] = frozenset()
    max_age: timedelta | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> ReadScope:
        """Build the scope from the mailbox settings."""
        for label in settings.read_labels:
            if FORBIDDEN_LABEL_CHARS & set(label):
                raise ScopeError(f"READ_LABELS entry contains a forbidden character: {label!r}")
        return cls(labels=frozenset(settings.read_labels), max_age=settings.read_max_age)

    @property
    def unrestricted(self) -> bool:
        """True when every message is in scope."""
        return not self.labels and self.max_age is None


def normalise_label(label: str | bytes) -> str:
    """Map a configured or reported label to one comparable form."""
    text = label.decode("utf-8", errors="replace") if isinstance(label, bytes) else label
    for config_name, (reported, _) in SYSTEM_LABELS.items():
        if text.casefold() in (config_name, reported.casefold()):
            return reported
    return text


def in_scope(
    labels: Iterable[str | bytes],
    internal_date: datetime,
    scope: ReadScope,
    now: datetime,
) -> bool:
    """Decide whether one message may be read.

    Args:
        labels: The message's X-GM-LABELS.
        internal_date: When Gmail received it (INTERNALDATE), which the
            sender cannot forge, unlike the Date header.
        scope: The configured read scope.
        now: The current time, timezone-aware.
    """
    if scope.max_age is not None and internal_date < now - scope.max_age:
        return False
    if not scope.labels:
        return True
    allowed = {normalise_label(label) for label in scope.labels}
    return any(normalise_label(label) in allowed for label in labels)


def label_term(label: str) -> str:
    """Render one label as a Gmail search term."""
    system_term = SEARCH_TERMS.get(normalise_label(label))
    return system_term or f'label:"{label}"'


def gmail_filter(scope: ReadScope, now: datetime) -> str:
    """Return a Gmail search prefix that narrows results to the scope."""
    terms: list[str] = []
    if scope.labels:
        terms.append("(" + " OR ".join(label_term(label) for label in sorted(scope.labels)) + ")")
    if scope.max_age is not None:
        # after: has day granularity, so start a day early; in_scope is exact.
        cutoff = now - scope.max_age - timedelta(days=1)
        terms.append(f"after:{cutoff:%Y/%m/%d}")
    return " ".join(terms)
