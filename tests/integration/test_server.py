"""The MCP tools end to end, in process, against the fake IMAP client."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from email import message_from_bytes
from typing import Any

import anyio
import pytest
from imapclient.exceptions import IMAPClientError
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from email_assistance_agent import server
from email_assistance_agent.mail.search import MessageNotFound
from tests.fakes import DRAFTS_FOLDER, NOW, FakeImap, FakeMail, make_raw

FORBIDDEN_WORDS = ("send", "delete", "move", "expunge", "trash", "flag")


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> FakeImap:
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    monkeypatch.setenv("EMAIL_SIGNATURE", "Me\\nExample Ltd")
    monkeypatch.setenv("READ_LABELS", "Clients")
    monkeypatch.setenv("READ_MAX_AGE_DAYS", "30")
    fake = FakeImap(
        messages=[
            FakeMail(1, make_raw(cc="carol@example.org"), NOW - timedelta(days=1), (b"Clients",), 77),
            FakeMail(2, make_raw(subject="private"), NOW, (b"Personal",), 78),
            FakeMail(
                3, make_raw(extra_headers=[("X-Drafted-By", "email-assistance-agent")]), folder=DRAFTS_FOLDER
            ),
        ]
    )

    @contextmanager
    def fake_session(settings: object) -> Iterator[FakeImap]:
        yield fake

    monkeypatch.setattr(server, "session", fake_session)
    monkeypatch.setattr(server, "now", lambda: NOW)
    return fake


async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    result = await server.server.call_tool(name, arguments)
    assert isinstance(result, CallToolResult)
    return result


def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = anyio.run(call_tool, name, arguments)
    assert not result.is_error
    structured = result.structured_content
    assert isinstance(structured, dict)
    return structured


def list_tools() -> list[Any]:
    return anyio.run(server.server.list_tools)


def test_tool_set_is_exactly_the_allowlist() -> None:
    assert {tool.name for tool in list_tools()} == server.ALLOWED_TOOLS


def test_no_tool_name_suggests_sending_or_touching_other_mail() -> None:
    names = {tool.name for tool in list_tools()}

    # delete_draft is the one deleting tool, and it only reaches the service's own drafts.
    assert not [n for n in names - {"delete_draft"} for word in FORBIDDEN_WORDS if word in n]
    assert not [n for n in names if "send" in n or "move" in n or "trash" in n]


def test_every_description_marks_email_as_untrusted() -> None:
    for tool in list_tools():
        assert server.UNTRUSTED_NOTICE in (tool.description or ""), tool.name


def test_writes_and_destructive_tools_are_exactly_the_draft_tools() -> None:
    annotations = {tool.name: tool.annotations for tool in list_tools()}

    writers = sorted(n for n, a in annotations.items() if not a.read_only_hint)
    destructive = sorted(n for n, a in annotations.items() if a.destructive_hint)
    assert writers == ["compose_draft", "create_draft", "delete_draft", "update_draft"]
    assert destructive == ["delete_draft", "update_draft"]


def test_tools_list_without_any_configuration() -> None:
    assert len(list_tools()) == len(server.ALLOWED_TOOLS)


def test_search_returns_only_scoped_summaries(mailbox: FakeImap) -> None:
    result = call("search", {"query": "report"})

    assert result["status"] == "ok"
    assert [m["uid"] for m in result["data"]] == [1]
    assert "content_untrusted" not in result["data"][0]
    assert mailbox.logged_out is False  # the fake session does not log out


def test_read_message_marks_body_untrusted(mailbox: FakeImap) -> None:
    data = call("read_message", {"uid": 1})["data"]

    assert data["content_untrusted"].startswith("Hello,")
    assert data["thread_id"] == "77"
    assert data["labels"] == ["Clients"]


def test_out_of_scope_message_is_not_found(mailbox: FakeImap) -> None:
    result = call("read_message", {"uid": 2})

    assert result == {"status": "error", "data": None, "error": "Message 2 was not found."}


def test_read_thread(mailbox: FakeImap) -> None:
    data = call("read_thread", {"uid": 1})["data"]

    assert [m["uid"] for m in data["messages"]] == [1]
    assert data["omitted_out_of_scope"] == 0


def test_list_drafts(mailbox: FakeImap) -> None:
    data = call("list_drafts", {})["data"]

    assert [d["uid"] for d in data] == [3]


def test_create_draft_threads_quotes_and_signs(mailbox: FakeImap) -> None:
    data = call("create_draft", {"reply_to_uid": 1, "body": "Will do. [TODO: date]", "reply_all": True})[
        "data"
    ]

    assert data == {
        "draft_uid": 42,
        "to": "Alice <alice@example.org>",
        "cc": "carol@example.org",
        "subject": "Re: Project update",
    }
    folder, raw, flags, _ = mailbox.appended[0]
    draft = message_from_bytes(raw)
    assert (folder, flags) == (DRAFTS_FOLDER, (b"\\Draft",))
    assert draft["In-Reply-To"] == "<orig-1@example.org>"
    payload = draft.get_payload(decode=True)
    assert isinstance(payload, bytes)
    text = payload.decode()
    assert "Will do. [TODO: date]\n\n-- \nMe\nExample Ltd\n\nOn " in text


def test_create_draft_refuses_out_of_scope_original(mailbox: FakeImap) -> None:
    result = call("create_draft", {"reply_to_uid": 2, "body": "hi"})

    assert result["error"] == "Message 2 was not found."
    assert mailbox.appended == []


def test_invalid_arguments_are_rejected_before_any_mail_access(mailbox: FakeImap) -> None:
    cases: list[tuple[str, dict[str, Any]]] = [
        ("read_message", {"uid": 0}),
        ("search", {"query": ""}),
        ("search", {"query": "x", "limit": 51}),
        ("create_draft", {"reply_to_uid": 1, "body": ""}),
        ("create_draft", {"reply_to_uid": 1, "body": "x" * (server.MAX_DRAFT_BODY_CHARS + 1)}),
    ]
    for name, arguments in cases:
        with pytest.raises(ToolError):
            anyio.run(call_tool, name, arguments)
    assert mailbox.selections == []


@pytest.mark.parametrize(
    ("error", "outcome", "message"),
    [
        (MessageNotFound(9), "rejected", "Message 9 was not found."),
        (IMAPClientError("server said: subject Secret"), "mail_error", "The mail server could not"),
        (TimeoutError("timed out"), "mail_error", "The mail server could not"),
        (RuntimeError("body text Secret"), "internal_error", "Internal error."),
    ],
)
def test_errors_become_safe_envelopes(
    error: Exception, outcome: str, message: str, caplog: pytest.LogCaptureFixture
) -> None:
    def action() -> Any:
        raise error

    with caplog.at_level("INFO"):
        result = server.run_tool("read_message", [9], action)

    assert result["status"] == "error"
    assert result["error"].startswith(message)
    assert "Secret" not in result["error"]
    assert [r for r in caplog.records if getattr(r, "outcome", None) == outcome]


def test_mail_errors_log_the_server_detail(caplog: pytest.LogCaptureFixture) -> None:
    def action() -> Any:
        raise IMAPClientError("[ALERT] Too many simultaneous connections")

    server.run_tool("search", [], action)

    warning = next(r for r in caplog.records if r.getMessage() == "Mail server error")
    assert getattr(warning, "detail", "").startswith("[ALERT] Too many")


def test_every_call_logs_its_start_and_end(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        server.run_tool("search", [], lambda: [])

    assert [r.getMessage() for r in caplog.records] == ["Tool call started", "Tool call"]


def test_compose_draft_creates_a_new_signed_draft(mailbox: FakeImap) -> None:
    data = call("compose_draft", {"to": ["aspast@example.org"], "subject": "hi", "body": "hello there"})[
        "data"
    ]

    assert data == {"draft_uid": 42, "to": "aspast@example.org", "cc": "", "subject": "hi"}
    folder, raw, flags, _ = mailbox.appended[0]
    draft = message_from_bytes(raw)
    assert (folder, flags) == (DRAFTS_FOLDER, (b"\\Draft",))
    assert "In-Reply-To" not in draft
    payload = draft.get_payload(decode=True)
    assert isinstance(payload, bytes)
    assert payload.decode() == "hello there\n\n-- \nMe\nExample Ltd\n"


def test_compose_draft_rejects_addresses_with_names_or_separators(mailbox: FakeImap) -> None:
    for to in (["Alice <a@example.org>"], ["a@example.org, b@example.org"], []):
        with pytest.raises(ToolError):
            anyio.run(call_tool, "compose_draft", {"to": to, "subject": "hi", "body": "x"})
    assert mailbox.appended == []


def agent_reply_draft(uid: int) -> FakeMail:
    raw = (
        b"From: me@example.com\nTo: Alice <alice@example.org>\nSubject: Re: Project update\n"
        b"Message-ID: <d1@example.com>\nIn-Reply-To: <orig-1@example.org>\n"
        b"X-Drafted-By: email-assistance-agent\n\nfirst version\n"
    )
    return FakeMail(uid, raw, folder=DRAFTS_FOLDER)


def test_update_draft_replaces_a_reply_in_place(mailbox: FakeImap) -> None:
    mailbox.messages.append(agent_reply_draft(9))

    data = call("update_draft", {"draft_uid": 9, "body": "second version"})["data"]

    assert data == {
        "draft_uid": 42,
        "to": "Alice <alice@example.org>",
        "cc": "",
        "subject": "Re: Project update",
    }
    assert mailbox.deleted == [(DRAFTS_FOLDER, 9)]
    new = message_from_bytes(mailbox.appended[0][1])
    assert new["In-Reply-To"] == "<orig-1@example.org>"
    payload = new.get_payload(decode=True)
    assert isinstance(payload, bytes)
    assert payload.decode().startswith("second version\n\n-- \nMe\nExample Ltd\n\nOn ")


def test_update_draft_rejects_a_new_subject_for_a_reply(mailbox: FakeImap) -> None:
    mailbox.messages.append(agent_reply_draft(9))

    result = call("update_draft", {"draft_uid": 9, "body": "x", "subject": "other"})

    assert result["status"] == "error" and "keeps the subject" in result["error"]
    assert mailbox.appended == [] and mailbox.deleted == []


def test_update_draft_of_a_new_email_can_change_subject(mailbox: FakeImap) -> None:
    call("compose_draft", {"to": ["aspast@example.org"], "subject": "hi", "body": "v1"})
    raw = mailbox.appended[0][1]
    mailbox.messages.append(FakeMail(10, raw, folder=DRAFTS_FOLDER))

    data = call("update_draft", {"draft_uid": 10, "body": "v2", "subject": "hello"})["data"]

    assert (data["to"], data["subject"]) == ("aspast@example.org", "hello")
    assert mailbox.deleted == [(DRAFTS_FOLDER, 10)]


def test_delete_draft_removes_only_agent_drafts(mailbox: FakeImap) -> None:
    assert call("delete_draft", {"draft_uid": 3})["data"] == {"deleted_draft_uid": 3}
    assert mailbox.deleted == [(DRAFTS_FOLDER, 3)]

    mailbox.messages.append(FakeMail(11, make_raw(subject="owner draft"), folder=DRAFTS_FOLDER))
    result = call("delete_draft", {"draft_uid": 11})

    assert result["error"] == "Draft 11 was not found."
    assert mailbox.deleted == [(DRAFTS_FOLDER, 3)]
