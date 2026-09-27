"""An in-memory stand-in for IMAPClient, recording every call it receives.

It deliberately has no methods that change flags or delete anything, so a
code path that tries to would fail with AttributeError.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any

from imapclient.imapclient import ALL, DRAFTS

ALL_MAIL = "[Gmail]/All Mail"
DRAFTS_FOLDER = "[Gmail]/Drafts"
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class FakeMail:
    uid: int
    raw: bytes
    internal_date: datetime = NOW
    labels: tuple[bytes, ...] = (b"\\Inbox",)
    thread_id: int = 1000
    folder: str = ALL_MAIL


def make_raw(
    *,
    sender: str = "Alice <alice@example.org>",
    to: str = "me@example.com",
    subject: str = "Project update",
    message_id: str | None = "<orig-1@example.org>",
    body: str = "Hello,\nplease send the report.",
    cc: str | None = None,
    reply_to: str | None = None,
    references: str | None = None,
    date: datetime = NOW,
    html: str | None = None,
    extra_headers: Sequence[tuple[str, str]] = (),
) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = format_datetime(date)
    if message_id:
        msg["Message-ID"] = message_id
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    if references:
        msg["References"] = references
    for name, value in extra_headers:
        msg[name] = value
    if html is None:
        msg.set_content(body)
    else:
        msg.set_content(html, subtype="html")
    return msg.as_bytes()


@dataclass
class FakeImap:
    messages: list[FakeMail] = field(default_factory=list)
    special_folders: dict[bytes, str] = field(default_factory=lambda: {ALL: ALL_MAIL, DRAFTS: DRAFTS_FOLDER})
    append_response: bytes = b"[APPENDUID 7 42] (Success)"
    gmail_results: list[int] | None = None
    selected: str | None = None
    selections: list[tuple[str, bool]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    appended: list[tuple[str, bytes, tuple[bytes, ...], datetime | None]] = field(default_factory=list)
    fetched_items: list[list[str]] = field(default_factory=list)
    logged_out: bool = False
    normalise_times: bool = True

    def login(self, username: str, password: str) -> None:
        self.credentials = (username, password)

    def logout(self) -> None:
        self.logged_out = True

    def find_special_folder(self, flag: bytes) -> str | None:
        return self.special_folders.get(flag)

    def select_folder(self, folder: str, readonly: bool = False) -> dict[bytes, Any]:
        self.selected = folder
        self.selections.append((folder, readonly))
        return {}

    def in_folder(self) -> list[FakeMail]:
        return [m for m in self.messages if m.folder == self.selected]

    def gmail_search(self, query: str, charset: str = "UTF-8") -> list[int]:
        self.queries.append(query)
        if self.gmail_results is not None:
            return list(self.gmail_results)
        return [m.uid for m in self.in_folder()]

    def search(self, criteria: Sequence[Any] = "ALL", charset: str | None = None) -> list[int]:
        if criteria[0] == "X-GM-THRID":
            return [m.uid for m in self.in_folder() if m.thread_id == criteria[1]]
        if criteria[0] == "HEADER":
            needle = f"{criteria[1]}: {criteria[2]}".encode()
            return [m.uid for m in self.in_folder() if needle in m.raw]
        raise AssertionError(f"unexpected search {criteria!r}")

    def fetch(self, uids: Iterable[int], items: Sequence[str]) -> dict[int, dict[bytes, Any]]:
        self.fetched_items.append(list(items))
        wanted = set(uids)
        return {m.uid: self.fetch_one(m, items) for m in self.in_folder() if m.uid in wanted}

    def fetch_one(self, mail: FakeMail, items: Sequence[str]) -> dict[bytes, Any]:
        data: dict[bytes, Any] = {b"SEQ": mail.uid}
        for item in items:
            if item == "X-GM-LABELS":
                data[b"X-GM-LABELS"] = mail.labels
            elif item == "INTERNALDATE":
                data[b"INTERNALDATE"] = mail.internal_date
            elif item == "X-GM-THRID":
                data[b"X-GM-THRID"] = mail.thread_id
            elif item.startswith("BODY.PEEK[HEADER.FIELDS"):
                headers, _, _ = mail.raw.partition(b"\n\n")
                data[b"BODY[HEADER.FIELDS (MESSAGE-ID FROM)]"] = headers + b"\n\n"
            elif item == "BODY.PEEK[]":
                data[b"BODY[]"] = mail.raw
            else:
                raise AssertionError(f"unexpected fetch item {item!r}")
        return data

    def append(
        self, folder: str, msg: bytes, flags: tuple[bytes, ...] = (), msg_time: datetime | None = None
    ) -> bytes:
        self.appended.append((folder, msg, tuple(flags), msg_time))
        return self.append_response
