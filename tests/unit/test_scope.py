from __future__ import annotations

from datetime import timedelta

import pytest

from email_assistance_agent.mail.scope import ReadScope, ScopeError, gmail_filter, in_scope, normalise_label
from tests.conftest import make_settings
from tests.fakes import NOW


def test_unrestricted_scope_allows_everything() -> None:
    scope = ReadScope()

    assert scope.unrestricted
    assert in_scope([], NOW - timedelta(days=3650), scope, NOW)


def test_one_matching_label_is_enough() -> None:
    scope = ReadScope(labels=frozenset({"Clients", "INBOX"}))

    assert in_scope([b"Other", b"\\Inbox"], NOW, scope, NOW)
    assert in_scope(["Clients"], NOW, scope, NOW)


def test_no_matching_label_is_out_of_scope() -> None:
    scope = ReadScope(labels=frozenset({"Clients"}))

    assert not in_scope([b"\\Inbox", b"Personal"], NOW, scope, NOW)
    assert not in_scope([], NOW, scope, NOW)


def test_age_uses_internal_date() -> None:
    scope = ReadScope(max_age=timedelta(days=30))

    assert in_scope([], NOW - timedelta(days=29), scope, NOW)
    assert not in_scope([], NOW - timedelta(days=31), scope, NOW)


def test_label_and_age_must_both_hold() -> None:
    scope = ReadScope(labels=frozenset({"Clients"}), max_age=timedelta(days=7))

    assert not in_scope(["Clients"], NOW - timedelta(days=8), scope, NOW)


def test_inbox_label_forms_normalise_together() -> None:
    assert normalise_label("inbox") == normalise_label(b"\\Inbox") == "\\Inbox"
    assert normalise_label("Clients") == "Clients"


@pytest.mark.parametrize(
    ("configured", "reported"),
    [("SENT", b"\\Sent"), ("Starred", b"\\Starred"), ("important", b"\\Important")],
)
def test_system_labels_match_what_gmail_reports(configured: str, reported: bytes) -> None:
    scope = ReadScope(labels=frozenset({configured}))

    assert in_scope([reported], NOW, scope, NOW)
    assert not in_scope([b"\\Inbox"], NOW, scope, NOW)


def test_inbox_plus_sent_sees_both_sides_of_a_conversation() -> None:
    scope = ReadScope(labels=frozenset({"INBOX", "SENT"}))

    assert in_scope([b"\\Inbox"], NOW, scope, NOW)
    assert in_scope([b"\\Sent"], NOW, scope, NOW)
    assert not in_scope([b"Archive-only"], NOW, scope, NOW)
    assert gmail_filter(scope, NOW) == "(in:inbox OR in:sent)"


def test_system_labels_render_as_gmail_search_terms() -> None:
    scope = ReadScope(labels=frozenset({"STARRED", "IMPORTANT", "Key clients"}))

    assert gmail_filter(scope, NOW) == '(is:important OR label:"Key clients" OR is:starred)'


def test_gmail_filter_renders_labels_and_cutoff() -> None:
    scope = ReadScope(labels=frozenset({"INBOX", "Key clients"}), max_age=timedelta(days=30))

    assert gmail_filter(scope, NOW) == '(in:inbox OR label:"Key clients") after:2026/08/26'


def test_gmail_filter_is_empty_when_unrestricted() -> None:
    assert gmail_filter(ReadScope(), NOW) == ""


def test_from_settings() -> None:
    scope = ReadScope.from_settings(make_settings(read_labels=("Clients",), read_max_age_days=10))

    assert scope == ReadScope(labels=frozenset({"Clients"}), max_age=timedelta(days=10))


@pytest.mark.parametrize("label", ['a"b', "a(b", "a)b", "a\\b"])
def test_labels_that_could_break_the_query_are_rejected(label: str) -> None:
    with pytest.raises(ScopeError):
        ReadScope.from_settings(make_settings(read_labels=(label,)))
