from __future__ import annotations

import pytest

from email_assistance_agent.mail.compose import (
    MAX_RECIPIENTS,
    ComposeError,
    build_new_draft,
    normalise_recipients,
)

ME = "me@example.com"


def test_builds_an_unthreaded_marked_draft() -> None:
    draft = build_new_draft(["aspast@example.org"], "hi", "hello there", own_address=ME)

    assert (draft["From"], draft["To"], draft["Subject"]) == (ME, "aspast@example.org", "hi")
    assert "In-Reply-To" not in draft and "References" not in draft
    assert draft["X-Drafted-By"] == "email-assistance-agent"
    assert draft.get_content() == "hello there\n"


def test_signature_follows_the_body() -> None:
    draft = build_new_draft(["a@example.org"], "hi", "hello", own_address=ME, signature="Me\nACME")

    assert draft.get_content() == "hello\n\n-- \nMe\nACME\n"


def test_cc_drops_duplicates_of_to() -> None:
    draft = build_new_draft(
        ["a@example.org"], "hi", "x", own_address=ME, cc=["A@example.org", "b@example.org"]
    )

    assert draft["Cc"] == "b@example.org"


@pytest.mark.parametrize(
    "address",
    [
        "Alice <a@example.org>",
        "a@example.org, evil@example.org",
        '"a"@example.org',
        "a@example.org\nBcc: evil@example.org",
        "not-an-address",
        "",
    ],
)
def test_only_plain_addresses_are_accepted(address: str) -> None:
    with pytest.raises(ComposeError):
        normalise_recipients([address])


def test_needs_a_recipient() -> None:
    with pytest.raises(ComposeError, match="at least one"):
        build_new_draft([], "hi", "x", own_address=ME)


def test_caps_recipients() -> None:
    many = [f"p{i}@example.org" for i in range(MAX_RECIPIENTS + 1)]

    with pytest.raises(ComposeError, match="At most"):
        build_new_draft(many, "hi", "x", own_address=ME)


@pytest.mark.parametrize("subject", ["two\nlines", "x" * 251])
def test_subject_must_be_one_short_line(subject: str) -> None:
    with pytest.raises(ComposeError, match="subject"):
        build_new_draft(["a@example.org"], subject, "x", own_address=ME)
