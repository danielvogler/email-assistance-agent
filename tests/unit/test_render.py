from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from email_assistance_agent.mail.body import html_to_text
from email_assistance_agent.mail.render import ALLOWED_TAGS, Quote, draft_html, render_markdown


class TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.extend(attrs)


def collect(html: str) -> TagCollector:
    collector = TagCollector()
    collector.feed(html)
    collector.close()
    return collector


HOSTILE = [
    '<img src="https://tracker.example/p.gif">',
    "<script>alert(1)</script>",
    '<a href="javascript:alert(1)">click</a>',
    "[click](javascript:alert(1))",
    "[docs](https://evil.example/?q=secret)",
    '<span style="color:#fff;font-size:0">hidden</span>',
    '<div style="display:none">hidden</div>',
    "<style>p{display:none}</style>",
    "![x](https://tracker.example/p.gif)",
    "http://plain.example/insecure",
    "data:text/html;base64,PHNjcmlwdD4=",
    '"><img src=x onerror=alert(1)>',
    "**<b>bold</b>** and *<i>it</i>*",
    'https://example.org/a?b=1&c="x"><script>',
    "x\x00y",
]


@pytest.mark.parametrize("source", HOSTILE)
def test_hostile_input_yields_only_allowed_tags_and_safe_links(source: str) -> None:
    html = draft_html(source, source, Quote("Eve wrote:", (source,)))

    collected = collect(html)
    assert set(collected.tags) <= ALLOWED_TAGS
    for name, value in collected.attrs:
        assert name == "href"
        assert value is not None and value.startswith(("https://", "mailto:"))


def test_raw_html_is_escaped_and_stays_visible() -> None:
    assert render_markdown("<script>x</script>") == "<p>&lt;script&gt;x&lt;/script&gt;</p>"


def test_bold_and_italic() -> None:
    assert render_markdown("**done** and *soon*") == "<p><strong>done</strong> and <em>soon</em></p>"


def test_stray_asterisks_are_not_emphasis() -> None:
    assert render_markdown("5 * 3 * 2") == "<p>5 * 3 * 2</p>"


def test_https_url_becomes_a_link_showing_its_target() -> None:
    assert render_markdown("See https://example.org/a?b=1&c=2.") == (
        '<p>See <a href="https://example.org/a?b=1&amp;c=2">https://example.org/a?b=1&amp;c=2</a>.</p>'
    )


def test_email_address_becomes_a_mailto_link() -> None:
    assert render_markdown("Write to me@example.com") == (
        '<p>Write to <a href="mailto:me@example.com">me@example.com</a></p>'
    )


def test_named_links_are_not_rendered_so_text_never_hides_the_target() -> None:
    html = render_markdown("[our docs](https://evil.example/x)")

    assert ">our docs</a>" not in html
    assert '<a href="https://evil.example/x">https://evil.example/x</a>' in html


def test_asterisks_inside_a_url_are_kept() -> None:
    assert 'href="https://example.org/a*b"' in render_markdown("https://example.org/a*b")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("**https://a.example**", '<strong><a href="https://a.example">https://a.example</a></strong>'),
        ("*https://a.example*", '<em><a href="https://a.example">https://a.example</a></em>'),
    ],
)
def test_emphasis_around_a_url_stays_outside_the_link(source: str, expected: str) -> None:
    assert render_markdown(source) == f"<p>{expected}</p>"


def test_crossed_emphasis_never_mis_nests_tags() -> None:
    assert render_markdown("**bold *it** x*") == "<p><strong>bold *it</strong> x*</p>"


def test_italic_inside_bold() -> None:
    assert render_markdown("**a *b* c**") == "<p><strong>a <em>b</em> c</strong></p>"


def test_bidi_controls_end_a_link() -> None:
    assert render_markdown("https://ab\u202ec.example") == (
        '<p><a href="https://ab">https://ab</a>\u202ec.example</p>'
    )


def test_nul_inside_a_url_is_dropped() -> None:
    assert render_markdown("https://a.exa\x00mple") == (
        '<p><a href="https://a.example">https://a.example</a></p>'
    )


def test_a_bare_scheme_is_not_a_link() -> None:
    assert render_markdown("https://.") == "<p>https://.</p>"


def test_plain_http_is_not_linked() -> None:
    assert render_markdown("http://example.org") == "<p>http://example.org</p>"


def test_single_newlines_are_line_breaks_and_blank_lines_paragraphs() -> None:
    assert render_markdown("Name\nTitle\n\nNext") == "<p>Name<br>Title</p><p>Next</p>"


def test_dash_lines_become_a_list_after_a_lead_in() -> None:
    assert render_markdown("Points:\n- one\n* two\nAfter") == (
        "<p>Points:</p><ul><li>one</li><li>two</li></ul><p>After</p>"
    )


def test_numbered_lines_stay_as_written() -> None:
    assert render_markdown("1. one\n2. two") == "<p>1. one<br>2. two</p>"


def test_headings_stay_literal() -> None:
    assert render_markdown("# Title") == "<p># Title</p>"


def test_draft_html_orders_body_signature_quote() -> None:
    html = draft_html("Thanks!", "**Me**\nme@example.com", Quote("Alice wrote:", ("<b>hi</b>", "[...]")))

    assert html.index("Thanks!") < html.index("<strong>Me</strong>") < html.index("Alice wrote:")
    assert "<blockquote>&lt;b&gt;hi&lt;/b&gt;<br>[...]</blockquote>" in html


def test_draft_html_without_signature_or_quote() -> None:
    assert draft_html("Hi", None, None) == "<html><body><p>Hi</p></body></html>"


def visible_words(markdown: str) -> list[str]:
    """The words a reader sees in the text part, with Markdown markers removed."""
    lines = (re.sub(r"^\s*(?:[-*]\s+|>\s?)", "", line) for line in markdown.splitlines())
    return " ".join(lines).replace("**", "").replace("*", "").split()


@pytest.mark.parametrize(
    ("body", "signature"),
    [
        ("Hi Alice,\n\n**Yes**, *Friday* works.\n- agenda\n- notes\n\nBest", "**Me**\nme@example.com"),
        ("See https://example.org/x?a=1&b=2 and <b>this</b>", "Me"),
        ("1. first\n2. second\n\n# not a heading", None),
    ],
)
def test_html_shows_the_same_words_as_the_text_part(body: str, signature: str | None) -> None:
    quote = Quote("On Mon, Alice <alice@example.org> wrote:", ("hello & <there>", "", "bye"))
    text = "\n\n".join(filter(None, [body, f"-- \n{signature}" if signature else None]))
    text += "\n\n" + quote.attribution + "\n" + "\n".join("> " + line for line in quote.lines)

    assert html_to_text(draft_html(body, signature, quote)).split() == visible_words(text)
