"""One-line JSON logs, which Cloud Run turns into structured log entries."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

# Extra fields a log call may attach. Anything else passed as `extra` is
# dropped, so a careless call cannot put mail content into the logs.
ALLOWED_EXTRA_FIELDS = ("tool", "uids", "outcome", "duration_ms", "error_type", "detail")
RESERVED_RECORD_KEYS = frozenset(vars(logging.makeLogRecord({})))


class JsonFormatter(logging.Formatter):
    """Formats records as JSON with the `severity` key Cloud Logging reads."""

    def format(self, record: logging.LogRecord) -> str:
        """Render one record as a JSON line."""
        entry: dict[str, Any] = {
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ALLOWED_EXTRA_FIELDS:
            if key in vars(record) and key not in RESERVED_RECORD_KEYS:
                entry[key] = vars(record)[key]
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


# IMAPClient logs the raw IMAP conversation at DEBUG, and that includes message
# headers and bodies. These loggers stay at WARNING whatever LOG_LEVEL says.
MAIL_PROTOCOL_LOGGERS = ("imapclient", "imapclient.imaplib")
REDACTED = "**REDACTED**"


class RedactSecrets(logging.Filter):
    """Masks known secret values in any record, as a last line of defence."""

    def __init__(self, secrets: tuple[str, ...]) -> None:
        super().__init__()
        self.secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        """Replace secrets in the rendered message; never drop the record."""
        message = record.getMessage()
        if any(secret in message for secret in self.secrets):
            for secret in self.secrets:
                message = message.replace(secret, REDACTED)
            record.msg, record.args = message, None
        return True


def configure_logging(level: str, secrets: tuple[str, ...] = ()) -> None:
    """Send JSON logs to stderr at the given level. Call once, at startup."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactSecrets(secrets))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    for name in MAIL_PROTOCOL_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
