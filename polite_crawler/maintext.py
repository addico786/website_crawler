"""The main text of a page, one block (paragraph, heading, list item...) per line.

trafilatura drops menus, footers, cookie banners and side blocks. On pages it misreads
(listings, very short pages) it keeps too little, so the page's own text is used instead.
"""
import logging

import trafilatura

logger = logging.getLogger(__name__)

MAX_TRAFILATURA_BYTES = 5 * 1024 * 1024  # slow on huge pages; use the fallback there
# Text inside these is never page text. nav/header/footer: menus repeated on every page.
SKIP_TAGS = {"head", "script", "style", "noscript", "svg", "template", "nav", "header", "footer"}
# Elements that start a new line of text.
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "body", "br", "caption", "dd", "details", "div",
    "dl", "dt", "fieldset", "figcaption", "figure", "form", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "html", "li", "main", "ol", "option", "p", "pre", "section", "summary", "table", "td",
    "th", "tr", "ul",
}


def clean_lines(text):
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def page_text(root):
    """All visible text of the page outside SKIP_TAGS, one block per line."""
    parts = []
    stack = [(root, False)]  # not recursive: some pages nest deeper than Python allows
    while stack:
        element, closing = stack.pop()
        tag = element.tag.lower() if isinstance(element.tag, str) else None  # None: a comment
        if closing or tag is None or tag in SKIP_TAGS:
            if closing and tag in BLOCK_TAGS:
                parts.append("\n")
            if element.tail and element is not root:
                parts.append(element.tail)
            continue
        if tag in BLOCK_TAGS:
            parts.append("\n")
        if element.text:
            parts.append(element.text)
        stack.append((element, True))
        stack.extend((child, False) for child in reversed(element))
    return clean_lines(" ".join(parts))


def main_text(html, root):
    """(text, source): trafilatura's text, or the page's own ("fallback") when trafilatura
    fails or keeps under half of the page's words."""
    fallback = page_text(root)
    if len(html) > MAX_TRAFILATURA_BYTES:
        return fallback, "fallback"
    try:
        extracted = trafilatura.extract(
            html, favor_recall=True, include_tables=True, include_comments=False,
            with_metadata=False, deduplicate=False, output_format="txt",
        )
    except Exception as e:  # a parser bug must not lose the page
        logger.debug("trafilatura failed: %s", e)
        extracted = None
    text = clean_lines(extracted or "")
    if not text or len(text.split()) < len(fallback.split()) / 2:
        return fallback, "fallback"
    return text, "trafilatura"
