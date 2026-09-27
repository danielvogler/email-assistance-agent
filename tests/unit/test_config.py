from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from email_assistance_agent.config import ConfigError, get_settings, load_settings
from tests.conftest import make_settings


def test_missing_credentials_are_named_without_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMAP_PORT", "not-a-port-secret-ish")

    with pytest.raises(ConfigError) as excinfo:
        load_settings()

    message = str(excinfo.value)
    assert "EMAIL_USER" in message
    assert "EMAIL_PASSWORD" in message
    assert "IMAP_PORT" in message
    assert "not-a-port-secret-ish" not in message


def test_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    monkeypatch.setenv("READ_LABELS", "INBOX, Clients ,")
    monkeypatch.setenv("READ_MAX_AGE_DAYS", "30")
    monkeypatch.setenv("ALLOWED_HOSTS", "a.run.app,localhost:*")

    settings = load_settings()

    assert settings.read_labels == ("INBOX", "Clients")
    assert settings.read_max_age == timedelta(days=30)
    assert settings.allowed_hosts == ("a.run.app", "localhost:*")
    assert settings.email_password.get_secret_value() == "pw"


def test_loads_dotenv_from_working_directory(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("EMAIL_USER=me@example.com\nEMAIL_PASSWORD=pw\n")

    assert load_settings().email_user == "me@example.com"


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")

    assert get_settings() is get_settings()


def test_defaults() -> None:
    settings = make_settings()

    assert settings.imap_host == "imap.gmail.com"
    assert settings.imap_port == 993
    assert settings.read_labels == ()
    assert settings.read_max_age is None
    assert settings.mail_domain == "example.com"
    assert "test-app-password" not in repr(settings)


def test_rejects_invalid_address() -> None:
    with pytest.raises(ValidationError):
        make_settings(email_user="not-an-address")


def test_settings_are_immutable() -> None:
    settings = make_settings()

    with pytest.raises(ValidationError):
        settings.imap_host = "evil.example.com"  # type: ignore[misc]


def test_signature_accepts_escaped_newlines() -> None:
    assert make_settings(email_signature="Daniel\\nACME").email_signature == "Daniel\nACME"


def test_empty_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    for name in ("IMAP_PORT", "READ_LABELS", "READ_MAX_AGE_DAYS", "ALLOWED_HOSTS", "LOG_LEVEL"):
        monkeypatch.setenv(name, "")

    settings = load_settings()

    assert (settings.imap_port, settings.read_labels, settings.log_level) == (993, (), "INFO")
    assert settings.allowed_hosts == ("localhost:*", "127.0.0.1:*")
