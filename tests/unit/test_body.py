from __future__ import annotations

from email.message import EmailMessage

from email_assistance_agent.mail.body import extract_body, html_to_text
from email_assistance_agent.mail.fetch import parse_message


def test_prefers_plain_text_in_multipart_alternative() -> None:
    msg = EmailMessage()
    msg.set_content("plain version")
    msg.add_alternative("<p>html version</p>", subtype="html")

    assert extract_body(msg).text == "plain version"


def test_falls_back_to_html_without_plain_part() -> None:
    msg = EmailMessage()
    msg.set_content(
        "<html><head><style>p{}</style></head><body><p>Hi&nbsp;there</p>"
        "<script>evil()</script><div>Second</div></body></html>",
        subtype="html",
    )

    assert extract_body(msg).text == "Hi there\nSecond"


def test_decodes_declared_charset() -> None:
    raw = (
        b"Content-Type: text/plain; charset=iso-8859-1\n"
        b"Content-Transfer-Encoding: 8bit\n\n"
        b"Gr\xfc\xdfe aus Z\xfcrich"
    )

    assert extract_body(parse_message(raw)).text == "Grüße aus Zürich"


def test_undecodable_bytes_are_replaced_not_raised() -> None:
    raw = b"Content-Type: text/plain; charset=utf-8\nContent-Transfer-Encoding: 8bit\n\nok \xff\xfe end"

    assert extract_body(parse_message(raw)).text == "ok �� end"


def test_unknown_charset_falls_back_to_utf8() -> None:
    raw = b"Content-Type: text/plain; charset=x-made-up\nContent-Transfer-Encoding: 8bit\n\nhello"

    assert extract_body(parse_message(raw)).text == "hello"


def test_truncates_long_bodies_and_flags_it() -> None:
    msg = EmailMessage()
    msg.set_content("x" * 50)

    body = extract_body(msg, max_chars=10)

    assert body.text == "x" * 10
    assert body.truncated is True


def test_ignores_text_attachments() -> None:
    msg = EmailMessage()
    msg.set_content("the body")
    msg.add_attachment("attached text", subtype="plain", filename="a.txt")

    assert extract_body(msg).text == "the body"


def test_message_without_text_parts_is_empty() -> None:
    msg = EmailMessage()
    msg.set_content(b"\x00\x01", maintype="application", subtype="octet-stream")

    body = extract_body(msg)

    assert body.text == ""
    assert body.truncated is False


def test_html_to_text_collapses_whitespace() -> None:
    assert html_to_text("<p>  a   b </p>\n\n<p>c</p>") == "a b\nc"
