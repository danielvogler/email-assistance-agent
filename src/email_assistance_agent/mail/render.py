"""Render the Markdown subset drafts are written in as safe HTML.

The model writes a draft body in a small Markdown subset; the text part of
the draft keeps that source and the HTML part is rendered from it here, so
the two cannot say different things. Everything is escaped first. The only
markup this module ever emits is in ALLOWED_TAGS, and the only attribute is
an `href` to an `https:` or `mailto:` target that is also the visible link
text. There are no images, styles or remote resources, so opening a draft
loads nothing and the reviewer sees everything that is there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from itertools import groupby

ALLOWED_TAGS = frozenset({"html", "body", "p", "br", "strong", "em", "ul", "li", "a", "blockquote"})
SIGNATURE_DELIMITER_HTML = "<p>-- </p>"
# ASCII only, so bidi controls and look-alike letters cannot hide in a link.
URL_PATTERN = r"https://[!#-&(-;=?-_a-~]+"
EMAIL_PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
LINK = re.compile(rf"(?P<url>{URL_PATTERN})|(?P<email>{EMAIL_PATTERN})")
# Punctuation that ends a sentence rather than a URL ("see https://x.org."),
# and emphasis markers around one ("**https://x.org**").
URL_TRAILING_PUNCTUATION = ".,;:!?)]}*"
MIN_URL_CHARS = len("https://x")
BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
# Applied after BOLD and never across a tag, so emphasis cannot mis-nest.
ITALIC = re.compile(r"\*(?=[^\s*])([^<>]+?)(?<=[^\s*])\*")
LIST_ITEM = re.compile(r"^[-*]\s+(?P<item>.*)$")
BLANK_LINE = re.compile(r"\n[ \t]*\n")
# NUL never occurs in mail text; it is stripped from input and marks where a link goes.
PLACEHOLDER = re.compile("\x00(\\d+)\x00")


@dataclass(frozen=True)
class Quote:
    """The quoted original below a reply: who wrote it, and its text lines."""

    attribution: str
    lines: tuple[str, ...]


def anchor(target: str, *, is_email: bool) -> str:
    """A link whose visible text is exactly its target."""
    href = f"mailto:{target}" if is_email else target
    return f'<a href="{escape(href)}">{escape(target)}</a>'


def render_inline(line: str) -> str:
    """Escape one line, then mark up links, bold and italic."""
    text = line.replace("\x00", "")
    links: list[str] = []
    pieces: list[str] = []
    position = 0
    for match in LINK.finditer(text):
        target = match.group(0)
        if match.group("url"):
            target = target.rstrip(URL_TRAILING_PUNCTUATION)
            if len(target) < MIN_URL_CHARS:
                continue
        pieces += [text[position : match.start()], f"\x00{len(links)}\x00"]
        links.append(anchor(target, is_email=bool(match.group("email"))))
        position = match.start() + len(target)
    pieces.append(text[position:])
    html = escape("".join(pieces))
    html = ITALIC.sub(r"<em>\1</em>", BOLD.sub(r"<strong>\1</strong>", html))
    return PLACEHOLDER.sub(lambda m: links[int(m.group(1))], html)


def render_block(block: str) -> str:
    """One paragraph: runs of `- ` or `* ` lines become a list, other lines break with <br>."""
    html: list[str] = []
    matches = ((line, LIST_ITEM.match(line)) for line in block.split("\n"))
    for is_list, run in groupby(matches, key=lambda pair: pair[1] is not None):
        if is_list:
            items = "".join(f"<li>{render_inline(m.group('item'))}</li>" for _, m in run if m)
            html.append(f"<ul>{items}</ul>")
        else:
            html.append("<p>" + "<br>".join(render_inline(line) for line, _ in run) + "</p>")
    return "".join(html)


def render_markdown(text: str) -> str:
    """Render the subset: paragraphs, line breaks, `-` lists, **bold**, *italic*, autolinks."""
    blocks = BLANK_LINE.split(text.replace("\r\n", "\n").strip())
    return "".join(render_block(block) for block in blocks if block.strip())


def render_quote(quote: Quote) -> str:
    """The quoted original as escaped text only, never its own HTML."""
    lines = "<br>".join(escape(line) for line in quote.lines)
    return f"<p>{escape(quote.attribution)}</p><blockquote>{lines}</blockquote>"


def draft_html(body: str, signature: str | None, quote: Quote | None) -> str:
    """The HTML part of a draft: body, then signature, then the quoted original."""
    sections = [render_markdown(body)]
    if signature and signature.strip():
        sections.append(SIGNATURE_DELIMITER_HTML + render_markdown(signature))
    if quote is not None:
        sections.append(render_quote(quote))
    return "<html><body>" + "".join(sections) + "</body></html>"


def set_bodies(draft: EmailMessage, text: str, html: str) -> None:
    """Make `draft` multipart/alternative: the Markdown text, then its HTML rendering."""
    draft.set_content(text)
    draft.add_alternative(html, subtype="html")
