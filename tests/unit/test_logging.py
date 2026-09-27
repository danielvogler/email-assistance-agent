from __future__ import annotations

import json
import logging

import pytest

from email_assistance_agent.logging_setup import JsonFormatter, configure_logging


def record(**extra: object) -> logging.LogRecord:
    rec = logging.makeLogRecord({"name": "t", "levelname": "INFO", "levelno": 20, "msg": "Tool call"})
    rec.__dict__.update(extra)
    return rec


def test_formats_allowed_fields_and_drops_others() -> None:
    line = JsonFormatter().format(record(tool="search", uids=[1], body="secret mail text"))

    entry = json.loads(line)
    assert entry == {"severity": "INFO", "logger": "t", "message": "Tool call", "tool": "search", "uids": [1]}


def test_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        rec = record()
        rec.exc_info = sys.exc_info()

    assert "ValueError: boom" in json.loads(JsonFormatter().format(rec))["exception"]


def test_configure_logging_installs_json_handler() -> None:
    configure_logging("WARNING")

    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_imap_protocol_logs_stay_off_at_debug(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("DEBUG")

    logging.getLogger("imapclient.imaplib").debug("< * 1 FETCH (BODY[] {42} Subject: private)")
    logging.getLogger("imapclient").debug("> A1 FETCH 1 BODY.PEEK[]")
    logging.getLogger("email_assistance_agent").debug("own debug line")

    err = capsys.readouterr().err
    assert "private" not in err
    assert "FETCH" not in err
    assert "own debug line" in err


def test_known_secrets_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", secrets=("hunter2-app-password",))

    logging.getLogger("anything").warning("server said: bad password %s", "hunter2-app-password")

    err = capsys.readouterr().err
    assert "hunter2-app-password" not in err
    assert "**REDACTED**" in err
