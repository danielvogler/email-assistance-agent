"""Runtime configuration, read from the environment (and `.env` for local use).

On Cloud Run every value arrives as an environment variable, and the app
password is injected from Secret Manager. Locally, `.env` supplies the same
names for a test mailbox.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_ALLOWED_HOSTS = ("localhost:*", "127.0.0.1:*")
EMAIL_ADDRESS_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def split_csv(value: object) -> object:
    """Accept comma-separated strings for tuple fields set from env vars."""
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    return value


def unescape_newlines(value: object) -> object:
    r"""Let a one-line .env value use \n for line breaks in a signature."""
    if isinstance(value, str):
        return value.replace("\\n", "\n")
    return value


class Settings(BaseSettings):
    """Validated configuration for one mailbox."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # `KEY=` in .env means "use the default", as .env.example lists them.
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
    )

    email_user: str = Field(pattern=EMAIL_ADDRESS_PATTERN)
    email_password: SecretStr
    imap_host: str = "imap.gmail.com"
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_timeout_seconds: float = Field(default=30.0, gt=0)
    drafts_folder: str | None = None
    email_signature: str | None = None
    read_labels: Annotated[tuple[str, ...], NoDecode] = ()
    read_max_age_days: int | None = Field(default=None, ge=1)
    allowed_hosts: Annotated[tuple[str, ...], NoDecode] = DEFAULT_ALLOWED_HOSTS
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    _split_read_labels = field_validator("read_labels", mode="before")(split_csv)
    _unescape_signature = field_validator("email_signature", mode="before")(unescape_newlines)
    _split_allowed_hosts = field_validator("allowed_hosts", mode="before")(split_csv)

    @property
    def read_max_age(self) -> timedelta | None:
        """The maximum message age the server may read, if limited."""
        if self.read_max_age_days is None:
            return None
        return timedelta(days=self.read_max_age_days)

    @property
    def mail_domain(self) -> str:
        """The domain of the mailbox address, used for generated Message-IDs."""
        return self.email_user.rsplit("@", 1)[1]


def load_settings() -> Settings:
    """Build settings from the environment, failing with names but never values.

    Raises:
        ConfigError: If a required variable is missing or a value is invalid.
    """
    try:
        return Settings()
    except ValidationError as exc:
        problems = sorted(
            {f"{str(err['loc'][0]).upper()} ({err['type']})" for err in exc.errors() if err["loc"]}
        )
        raise ConfigError("Invalid or missing configuration: " + ", ".join(problems)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once on first use."""
    return load_settings()
