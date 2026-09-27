from __future__ import annotations

from datetime import timedelta

import pytest

from email_assistance_agent.mail.scope import ReadScope
from email_assistance_agent.mail.search import (
    MAX_THREAD_MESSAGES,
    EmptyQuery,
    MessageNotFound,
    clamp_limit,
    read_message,
    read_thread,
    scoped_query,
    search,
)
from tests.fakes import ALL_MAIL, NOW, FakeImap, FakeMail, make_raw

CLIENTS_ONLY = ReadScope(labels=frozenset({"Clients"}), max_age=timedelta(days=30))


def mailbox() -> FakeImap:
    return FakeImap(
        messages=[
            FakeMail(1, make_raw(subject="old client"), NOW - timedelta(days=60), (b"Clients",)),
            FakeMail(2, make_raw(subject="client"), NOW - timedelta(days=1), (b"Clients",)),
            FakeMail(3, make_raw(subject="personal"), NOW - timedelta(days=1), (b"Personal",)),
            FakeMail(4, make_raw(subject="newest client"), NOW, (b"Clients", b"\\Inbox")),
        ]
    )


def test_search_drops_out_of_scope_results_even_when_gmail_returns_them() -> None:
    client = mailbox()

    results = search(client, CLIENTS_ONLY, "report", 20, NOW)

    assert [m.uid for m in results] == [4, 2]
    assert client.selections == [(ALL_MAIL, True)]


def test_search_sends_scope_filter_with_grouped_query() -> None:
    client = mailbox()

    search(client, CLIENTS_ONLY, "from:alice) OR (in:anywhere", 20, NOW)

    assert client.queries == ['(label:"Clients") after:2026/08/26 ( from:alice) OR (in:anywhere )']


def test_query_is_always_sent_quoted() -> None:
    # Regression: IMAPClient leaves a space-free string unquoted, and Gmail
    # rejects "(newer_than:7d)" as an unparseable command.
    from imapclient.imapclient import _normalise_search_criteria

    query = scoped_query("newer_than:7d", ReadScope(), NOW)

    assert _normalise_search_criteria([b"X-GM-RAW", query])[1] == b'"( newer_than:7d )"'


def test_search_respects_limit() -> None:
    results = search(mailbox(), ReadScope(), "x", 1, NOW)

    assert [m.uid for m in results] == [4]


def test_blank_query_is_rejected() -> None:
    with pytest.raises(EmptyQuery):
        search(mailbox(), ReadScope(), "   ", 20, NOW)


@pytest.mark.parametrize(("given", "expected"), [(0, 1), (-5, 1), (20, 20), (500, 50)])
def test_clamp_limit(given: int, expected: int) -> None:
    assert clamp_limit(given) == expected


def test_read_message_returns_body_and_headers() -> None:
    message = read_message(mailbox(), CLIENTS_ONLY, 2, NOW)

    assert message.meta.uid == 2
    assert message.body.text == "Hello,\nplease send the report."
    assert message.meta.headers["Subject"] == "client"


@pytest.mark.parametrize("uid", [1, 3, 99])
def test_out_of_scope_and_missing_look_the_same(uid: int) -> None:
    with pytest.raises(MessageNotFound) as excinfo:
        read_message(mailbox(), CLIENTS_ONLY, uid, NOW)

    assert str(excinfo.value) == f"Message {uid} was not found."


def test_read_thread_returns_in_scope_messages_oldest_first() -> None:
    client = FakeImap(
        messages=[
            FakeMail(10, make_raw(subject="a"), NOW - timedelta(days=2), (b"Clients",), thread_id=7),
            FakeMail(11, make_raw(subject="b"), NOW - timedelta(days=1), (b"Personal",), thread_id=7),
            FakeMail(12, make_raw(subject="c"), NOW, (b"Clients",), thread_id=7),
            FakeMail(13, make_raw(subject="other"), NOW, (b"Clients",), thread_id=8),
        ]
    )

    thread = read_thread(client, CLIENTS_ONLY, 12, NOW)

    assert [m.meta.uid for m in thread.messages] == [10, 12]
    assert thread.omitted_out_of_scope == 1
    assert thread.omitted_over_limit == 0


def test_read_thread_keeps_the_newest_messages_over_the_cap() -> None:
    total = MAX_THREAD_MESSAGES + 2
    client = FakeImap(
        messages=[
            FakeMail(uid, make_raw(), NOW - timedelta(minutes=total - uid), thread_id=5)
            for uid in range(1, total + 1)
        ]
    )

    thread = read_thread(client, ReadScope(), 1, NOW)

    assert len(thread.messages) == MAX_THREAD_MESSAGES
    assert thread.messages[-1].meta.uid == total
    assert thread.omitted_over_limit == 2


def test_read_thread_rejects_out_of_scope_anchor() -> None:
    with pytest.raises(MessageNotFound):
        read_thread(mailbox(), CLIENTS_ONLY, 3, NOW)


def test_reading_never_fetches_without_peek() -> None:
    client = mailbox()

    read_thread(client, ReadScope(), 2, NOW)

    items = [item for call in client.fetched_items for item in call]
    assert all("PEEK" in item for item in items if item.startswith("BODY"))


def test_owners_unsent_drafts_are_invisible_but_agent_drafts_are_not() -> None:
    client = FakeImap(
        messages=[
            FakeMail(1, make_raw(subject="owner draft"), labels=(b"\\Draft",)),
            FakeMail(
                2, make_raw(extra_headers=[("X-Drafted-By", "email-assistance-agent")]), labels=(b"\\Draft",)
            ),
            FakeMail(3, make_raw(subject="received"), labels=(b"\\Inbox",)),
        ]
    )

    assert {m.uid for m in search(client, ReadScope(), "x", 20, NOW)} == {2, 3}
    with pytest.raises(MessageNotFound):
        read_message(client, ReadScope(), 1, NOW)
