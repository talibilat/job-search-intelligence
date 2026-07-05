from __future__ import annotations

import re
from html.parser import HTMLParser

_HTML_TAG_RE = re.compile(
    r"<\s*/?\s*[a-z][a-z0-9:-]*(?:\s[^<>]*)?/?>",
    re.IGNORECASE,
)


def email_body_contains_html(body_text: str) -> bool:
    return bool(_HTML_TAG_RE.search(body_text))


def normalize_email_html_to_text(html_body: str) -> str:
    parser = _EmailHTMLTextExtractor()
    parser.feed(html_body)
    parser.close()
    return parser.text


class _EmailHTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = frozenset(
        {
            "address",
            "article",
            "aside",
            "blockquote",
            "br",
            "div",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "hr",
            "li",
            "main",
            "ol",
            "p",
            "pre",
            "section",
            "table",
            "td",
            "th",
            "tr",
            "ul",
        }
    )
    _IGNORED_TAGS = frozenset(
        {
            "head",
            "math",
            "meta",
            "noscript",
            "script",
            "style",
            "svg",
            "title",
        }
    )
    _PUNCTUATION_WITHOUT_LEADING_SPACE = frozenset({".", ",", ";", ":", "!", "?", ")", "]", "}"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    @property
    def text(self) -> str:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized_tag = tag.lower()
        if normalized_tag in self._IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if normalized_tag in self._BLOCK_TAGS:
            self._append_break()

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in self._IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if normalized_tag in self._BLOCK_TAGS:
            self._append_break()

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._append_text(data)

    def _append_text(self, text: str) -> None:
        collapsed = re.sub(r"\s+", " ", text.replace("\xa0", " "))
        if not collapsed.strip():
            self._append_space()
            return

        starts_with_space = collapsed[0].isspace()
        ends_with_space = collapsed[-1].isspace()
        stripped = collapsed.strip()

        if starts_with_space:
            self._append_space()
        if self._needs_separator_before(stripped):
            self._append_space()
        self._parts.append(stripped)
        if ends_with_space:
            self._append_space()

    def _needs_separator_before(self, text: str) -> bool:
        if not self._parts:
            return False
        previous = self._parts[-1]
        return bool(
            previous
            and not previous[-1].isspace()
            and text[0] not in self._PUNCTUATION_WITHOUT_LEADING_SPACE
        )

    def _append_space(self) -> None:
        if self._parts and not self._parts[-1].endswith((" ", "\n")):
            self._parts.append(" ")

    def _append_break(self) -> None:
        if self._parts and not self._parts[-1].endswith("\n"):
            self._parts.append("\n")
