"""Shared fixtures.

Every test runs in an empty working directory with the mail variables cleared,
so a developer's real `.env` can never leak credentials into a test run.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from email_assistance_agent.config import Settings, get_settings

CONFIG_ENV_VARS = (
    "EMAIL_USER",
    "EMAIL_PASSWORD",
    "IMAP_HOST",
    "IMAP_PORT",
    "IMAP_TIMEOUT_SECONDS",
    "DRAFTS_FOLDER",
    "EMAIL_SIGNATURE",
    "READ_LABELS",
    "READ_MAX_AGE_DAYS",
    "ALLOWED_HOSTS",
    "PORT",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    for name in CONFIG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "email_user": "me@example.com",
        "email_password": "test-app-password",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]
