from __future__ import annotations

from datetime import timedelta

import pytest

from email_assistance_agent.mail.body import Body
from email_assistance_agent.mail.compose import build_new_draft
from email_assistance_agent.mail.draft_edit import (
    DraftError,
    DraftNotFound,
    delete_draft,
    replace_draft,
    revised_new_email,
    revised_reply,
)
from email_assistance_agent.mail.fetch import parse_message
from tests.fakes import ALL_MAIL, DRAFTS_FOLDER, NOW, FakeImap, FakeMail, make_raw

ME = "me@example.com"
MARK = [("X-Drafted-By", "email-assistance-agent")]


def mailbox() -> FakeImap:
    return FakeImap(
        messages=[
            FakeMail(5, make_raw(subject="agent draft", extra_headers=MARK), folder=DRAFTS_FOLDER),
            FakeMail(6, make_raw(subject="owner draft"), folder=DRAFTS_FOLDER),
            FakeMail(7, make_raw(subject="received"), folder=ALL_MAIL),
        ]
    )


def test_deletes_only_the_given_agent_draft() -> None:
    client = mailbox()

    delete_draft(client, DRAFTS_FOLDER, 5)

    assert client.deleted == [(DRAFTS_FOLDER, 5)]
    assert (DRAFTS_FOLDER, False) in client.selections


@pytest.mark.parametrize("uid", [6, 7, 99])
def test_owner_drafts_other_mail_and_missing_uids_are_not_found(uid: int) -> None:
    client = mailbox()

    with pytest.raises(DraftNotFound, match=f"Draft {uid} was not found"):
        delete_draft(client, DRAFTS_FOLDER, uid)

    assert client.deleted == []


def test_refuses_to_delete_without_uidplus() -> None:
    client = mailbox()
    client.uidplus = False

    with pytest.raises(DraftError, match="UIDPLUS"):
        delete_draft(client, DRAFTS_FOLDER, 5)

    assert client.deleted == []


def test_replace_appends_before_it_deletes() -> None:
    client = mailbox()
    new = build_new_draft(["a@example.org"], "v2", "second", own_address=ME)

    uid = replace_draft(client, DRAFTS_FOLDER, 5, new, NOW)

    assert uid == 42
    assert len(client.appended) == 1
    assert client.deleted == [(DRAFTS_FOLDER, 5)]


def test_replace_keeps_the_old_draft_when_it_is_not_ours() -> None:
    client = mailbox()
    new = build_new_draft(["a@example.org"], "v2", "second", own_address=ME)

    with pytest.raises(DraftNotFound):
        replace_draft(client, DRAFTS_FOLDER, 6, new, NOW)

    assert client.deleted == []


def test_revised_new_email_keeps_recipients_and_can_change_subject() -> None:
    old = parse_message(
        build_new_draft(["a@example.org"], "hi", "v1", own_address=ME, cc=["b@example.org"]).as_bytes()
    )

    new = revised_new_email(old, "v2", "hello", own_address=ME, signature="Me")

    assert (new["To"], new["Cc"], new["Subject"]) == ("a@example.org", "b@example.org", "hello")
    assert new.get_content() == "v2\n\n-- \nMe\n"


def test_revised_new_email_keeps_subject_by_default() -> None:
    old = parse_message(build_new_draft(["a@example.org"], "hi", "v1", own_address=ME).as_bytes())

    assert revised_new_email(old, "v2", None, own_address=ME, signature=None)["Subject"] == "hi"


def test_revised_reply_keeps_thread_and_recipients_of_the_old_draft() -> None:
    original = parse_message(make_raw(cc="carol@example.org", date=NOW - timedelta(days=1)))
    old = parse_message(
        b"From: me@example.com\nTo: Alice <alice@example.org>\nCc: carol@example.org\n"
        b"Subject: Re: Project update\nIn-Reply-To: <orig-1@example.org>\n"
        b"X-Drafted-By: email-assistance-agent\n\nv1\n"
    )

    new = revised_reply(old, original, Body("Hello", False), "v2 text", own_address=ME, signature=None)

    assert (new["To"], new["Cc"]) == ("Alice <alice@example.org>", "carol@example.org")
    assert new["In-Reply-To"] == "<orig-1@example.org>"
    assert new.get_content().startswith("v2 text\n\nOn ")
