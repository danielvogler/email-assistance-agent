from __future__ import annotations

from typing import Any

import pytest

from email_assistance_agent.mail import client as client_module
from email_assistance_agent.mail.client import all_mail_folder, drafts_folder, session
from tests.conftest import make_settings
from tests.fakes import FakeImap


class RecordingImap(FakeImap):
    def __init__(self, host: str, port: int, ssl: bool, timeout: float) -> None:
        super().__init__()
        self.opened_with = (host, port, ssl, timeout)


def test_session_logs_in_and_always_logs_out(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[RecordingImap] = []

    def factory(host: str, **kwargs: Any) -> RecordingImap:
        created.append(RecordingImap(host, **kwargs))
        return created[-1]

    monkeypatch.setattr(client_module, "IMAPClient", factory)

    with pytest.raises(RuntimeError), session(make_settings()) as client:
        assert client.credentials == ("me@example.com", "test-app-password")
        raise RuntimeError("tool failed")

    assert created[0].opened_with == ("imap.gmail.com", 993, True, 30.0)
    assert created[0].normalise_times is False
    assert created[0].logged_out


def test_logout_failure_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class BrokenLogout(FakeImap):
        def logout(self) -> None:
            raise OSError("connection reset")

    monkeypatch.setattr(client_module, "IMAPClient", lambda *a, **k: BrokenLogout())

    with session(make_settings()):
        pass

    assert "IMAP logout failed" in caplog.text


def test_special_use_folders_win() -> None:
    client = FakeImap(special_folders={b"\\All": "[Gmail]/Alle Nachrichten", b"\\Drafts": "[Gmail]/Entwürfe"})

    assert all_mail_folder(client) == "[Gmail]/Alle Nachrichten"
    assert drafts_folder(client, make_settings()) == "[Gmail]/Entwürfe"


def test_fallbacks_when_not_advertised() -> None:
    client = FakeImap(special_folders={})

    assert all_mail_folder(client) == "[Gmail]/All Mail"
    assert drafts_folder(client, make_settings()) == "[Gmail]/Drafts"
    assert drafts_folder(client, make_settings(drafts_folder="Brouillons")) == "Brouillons"
