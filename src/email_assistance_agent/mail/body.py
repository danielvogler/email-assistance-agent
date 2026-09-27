"""Extract readable text from a parsed email message."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import Message
from html.parser import HTMLParser

MAX_BODY_CHARS = 20_000
DEFAULT_CHARSET = "utf-8"
HTML_SKIPPED_TAGS = frozenset({"script", "style", "head", "title"})
HTML_BREAK_TAGS = frozenset({"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"})


@dataclass(frozen=True)
class Body:
    """Message text, and whether it was cut to fit the size cap."""

    text: str
    truncated: bool


class HtmlTextExtractor(HTMLParser):
    """Collects visible text from HTML, with line breaks at block elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track skipped elements and break lines at block starts."""
        if tag in HTML_SKIPPED_TAGS:
            self.skip_depth += 1
        elif tag in HTML_BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Leave skipped elements and break lines at block ends."""
        if tag in HTML_SKIPPED_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag in HTML_BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Keep text outside skipped elements."""
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """Strip tags from HTML, keeping paragraph breaks and dropping blank runs."""
    extractor = HtmlTextExtractor()
    extractor.feed(html)
    extractor.close()
    lines = (" ".join(line.split()) for line in "".join(extractor.parts).splitlines())
    return "\n".join(line for line in lines if line)


def decode_part(part: Message) -> str:
    """Decode one leaf part with its declared charset, never raising on bad bytes."""
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    charset = part.get_content_charset() or DEFAULT_CHARSET
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:  # an unknown charset name in the header
        return payload.decode(DEFAULT_CHARSET, errors="replace")


def first_part(msg: Message, content_type: str) -> Message | None:
    """Return the first non-attachment part of the given type."""
    for part in msg.walk():
        if part.get_content_type() == content_type and part.get_content_disposition() != "attachment":
            return part
    return None


def extract_body(msg: Message, max_chars: int = MAX_BODY_CHARS) -> Body:
    """Return the message text, preferring text/plain and falling back to HTML."""
    plain = first_part(msg, "text/plain")
    if plain is not None:
        text = decode_part(plain)
    else:
        html = first_part(msg, "text/html")
        text = html_to_text(decode_part(html)) if html is not None else ""
    text = text.replace("\r\n", "\n").strip()
    if len(text) > max_chars:
        return Body(text=text[:max_chars], truncated=True)
    return Body(text=text, truncated=False)
