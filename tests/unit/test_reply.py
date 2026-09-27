from __future__ import annotations

import pytest

from email_assistance_agent.mail.body import Body
from email_assistance_agent.mail.fetch import parse_message
from email_assistance_agent.mail.reply import ReplyError, build_reply, reply_subject
from tests.fakes import make_raw

ME = "me@example.com"
ORIGINAL_BODY = Body(text="Line one\nLine two", truncated=False)


def test_replies_to_sender_with_display_name() -> None:
    draft = build_reply(parse_message(make_raw()), ORIGINAL_BODY, "Hi", own_address=ME)

    assert draft["To"] == "Alice <alice@example.org>"
    assert draft["From"] == ME
    assert "Cc" not in draft


def test_reply_to_wins_over_from() -> None:
    raw = make_raw(reply_to="Team <team@example.org>")

    draft = build_reply(parse_message(raw), ORIGINAL_BODY, "Hi", own_address=ME)

    assert draft["To"] == "Team <team@example.org>"


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("Project", "Re: Project"),
        ("Re: Project", "Re: Project"),
        ("RE: Project", "RE: Project"),
        ("", "Re: "),
    ],
)
def test_subject_prefix_is_not_doubled(original: str, expected: str) -> None:
    assert reply_subject(original) == expected


def test_threading_headers_chain_references() -> None:
    raw = make_raw(message_id="<m2@example.org>", references="<m0@example.org> <m1@example.org>")

    draft = build_reply(parse_message(raw), ORIGINAL_BODY, "Hi", own_address=ME)

    assert draft["In-Reply-To"] == "<m2@example.org>"
    assert draft["References"] == "<m0@example.org> <m1@example.org> <m2@example.org>"
    assert draft["X-Drafted-By"] == "email-assistance-agent"
    assert str(draft["Message-ID"]).endswith("@example.com>")


def test_reply_all_excludes_self_sender_and_duplicates() -> None:
    raw = make_raw(to="Me <ME@example.com>, Bob <bob@example.org>", cc="bob@example.org, carol@example.org")

    draft = build_reply(parse_message(raw), ORIGINAL_BODY, "Hi", own_address=ME, reply_all=True)

    assert draft["Cc"] == "Bob <bob@example.org>, carol@example.org"


def test_cc_only_when_reply_all() -> None:
    raw = make_raw(cc="carol@example.org")

    draft = build_reply(parse_message(raw), ORIGINAL_BODY, "Hi", own_address=ME)

    assert "Cc" not in draft


def test_body_text_cannot_change_headers() -> None:
    raw = make_raw()

    draft = build_reply(
        parse_message(raw), ORIGINAL_BODY, "To: attacker@evil.test\nBcc: x@evil.test\n\nHi", own_address=ME
    )

    assert draft["To"] == "Alice <alice@example.org>"
    assert "Bcc" not in draft
    assert "attacker@evil.test" not in str(draft["To"])


def test_missing_message_id_raises() -> None:
    with pytest.raises(ReplyError, match="Message-ID"):
        build_reply(parse_message(make_raw(message_id=None)), ORIGINAL_BODY, "Hi", own_address=ME)


def test_missing_sender_raises() -> None:
    with pytest.raises(ReplyError, match="sender"):
        build_reply(parse_message(make_raw(sender="undisclosed")), ORIGINAL_BODY, "Hi", own_address=ME)


def test_own_message_has_no_one_to_reply_to() -> None:
    with pytest.raises(ReplyError, match="this mailbox"):
        build_reply(parse_message(make_raw(sender=ME)), ORIGINAL_BODY, "Hi", own_address=ME)


def test_body_order_text_signature_quote() -> None:
    draft = build_reply(
        parse_message(make_raw()), ORIGINAL_BODY, "Thanks!", own_address=ME, signature="Daniel\nACME"
    )

    text = draft.get_content()
    assert text.index("Thanks!") < text.index("-- \nDaniel\nACME") < text.index("wrote:")
    assert "On Sat, 26 Sep 2026 12:00:00 +0000, Alice <alice@example.org> wrote:" in text
    assert "> Line one\n> Line two" in text


def test_no_signature_block_when_unset() -> None:
    draft = build_reply(parse_message(make_raw()), ORIGINAL_BODY, "Thanks!", own_address=ME)

    assert "-- \n" not in draft.get_content()


def test_truncated_quote_ends_with_marker() -> None:
    draft = build_reply(
        parse_message(make_raw()), Body(text="partial", truncated=True), "Thanks!", own_address=ME
    )

    assert draft.get_content().rstrip().endswith("> partial\n> [...]")


def test_quote_without_date_uses_sender_only() -> None:
    raw = b"From: alice@example.org\nMessage-ID: <x@example.org>\nSubject: s\n\nbody\n"

    draft = build_reply(parse_message(raw), Body(text="", truncated=False), "Hi", own_address=ME)

    assert "alice@example.org wrote:\n>" in draft.get_content()
