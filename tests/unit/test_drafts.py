from __future__ import annotations

from email.message import EmailMessage

import pytest

from email_assistance_agent.mail.drafts import append_draft, list_drafts, parse_appenduid
from tests.fakes import DRAFTS_FOLDER, NOW, FakeImap, FakeMail, make_raw


def draft() -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Re: x"
    msg.set_content("hi")
    return msg


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (b"[APPENDUID 7 42] (Success)", 42),
        (b"[appenduid 1 9]", 9),
        ("[APPENDUID 3 5] done", 5),
        (b"APPEND completed", None),
    ],
)
def test_parse_appenduid(response: object, expected: int | None) -> None:
    assert parse_appenduid(response) == expected


def test_append_sets_only_the_draft_flag() -> None:
    client = FakeImap()

    uid = append_draft(client, DRAFTS_FOLDER, draft(), NOW)

    assert uid == 42
    folder, _, flags, when = client.appended[0]
    assert (folder, flags, when) == (DRAFTS_FOLDER, (b"\\Draft",), NOW)


def test_append_without_appenduid_returns_none(caplog: pytest.LogCaptureFixture) -> None:
    client = FakeImap(append_response=b"OK")

    assert append_draft(client, DRAFTS_FOLDER, draft(), NOW) is None
    assert "no APPENDUID" in caplog.text


def test_list_drafts_returns_only_agent_drafts() -> None:
    client = FakeImap(
        messages=[
            FakeMail(
                1, make_raw(extra_headers=[("X-Drafted-By", "email-assistance-agent")]), folder=DRAFTS_FOLDER
            ),
            FakeMail(2, make_raw(subject="human draft"), folder=DRAFTS_FOLDER),
            FakeMail(3, make_raw(extra_headers=[("X-Drafted-By", "someone-else")]), folder=DRAFTS_FOLDER),
        ]
    )

    drafts = list_drafts(client, DRAFTS_FOLDER, 20)

    assert [d.uid for d in drafts] == [1]
    assert client.selections == [(DRAFTS_FOLDER, True)]
