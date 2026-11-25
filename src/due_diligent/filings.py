"""Turn a 10-K's HTML into plain text, and find its sections (Item 1, 1A, 7, 8...).

Needs the edgar extra (beautifulsoup4): pip install -e ".[edgar]"
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Tags that start a new line in the page; table cells only get a space between them.
_BLOCK_TAGS = ["p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6"]
_CELL_TAGS = ["td", "th"]

# The sections the extraction needs: business (segments), risk factors, MD&A (guidance), financial statements
EXTRACT_ITEMS = ["1", "1a", "7", "8"]

# An Item 8 shorter than this is only a pointer ("set forth in our Consolidated Financial Statements...")
POINTER_MAX_CHARS = 2000

# A heading is a short line that starts "Item 1A." and so on. \b stops "Item 1" matching "Item 1A"
# or "Item 10". The 150-character limit skips sentences that start with a cross-reference,
# like "Item 1A of this report describes...".
_ITEM_HEADING = re.compile(
    r"^item\s+(1a|1b|1c|7a|9a|9b|9c|1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16)\b.{0,150}$",
    re.IGNORECASE | re.MULTILINE,
)


def filing_text(html: str) -> str:
    """The readable text of a filing: one line per paragraph or table row, no hidden content."""
    soup = BeautifulSoup(html, "html.parser")
    # Inline XBRL keeps a hidden copy of tagged facts at the top; it isn't part of the readable filing
    for hidden in soup.find_all(["ix:header", "script", "style"]):
        hidden.decompose()
    for hidden in soup.find_all(style=re.compile(r"display:\s*none", re.IGNORECASE)):
        hidden.decompose()
    # Add line breaks after blocks, spaces after cells; inline tags (span, b) join up as they read
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after("\n")
    for tag in soup.find_all(_CELL_TAGS):
        tag.insert_after(" ")
    lines = (" ".join(line.replace("\xa0", " ").split()) for line in soup.get_text().splitlines())
    return "\n".join(line for line in lines if line)


def find_sections(text: str) -> dict[str, str]:
    """Split the text at its 'Item N.' headings: {"1a": "Item 1A. Risk Factors ...", ...}.

    Each heading appears at least twice: once in the table of contents (a short span, just
    up to the next contents line) and once in the body (pages long). Keeping the longest
    span for each item picks the body.
    """
    starts: list[tuple[int, str]] = []
    for match in _ITEM_HEADING.finditer(text):
        item = match.group(1).lower()
        if starts and starts[-1][1] == item:
            continue  # a page header repeating the current item
        starts.append((match.start(), item))
    sections: dict[str, str] = {}
    for (start, item), (end, _) in zip(starts, starts[1:] + [(len(text), "")]):
        span = text[start:end].strip()
        if len(span) > len(sections.get(item, "")):
            sections[item] = span
    return sections

def extraction_text(text: str, items: list[str] = EXTRACT_ITEMS) -> tuple[str, bool]:
    """Only the sections the extraction needs, and whether that worked.

    Some filings (NVIDIA's, for one) leave Item 8 as a one-line pointer and print the
    financial statements under Item 15 instead. When Item 8 is that short, Item 15 is sent too.

    If any of the needed items can't be found, returns the whole text and False, so a filing
    with unusual headings costs more but still gets extracted.
    """
    sections = find_sections(text)
    if not all(item in sections for item in items):
        return text, False
    chosen = list(items)
    if len(sections.get("8", "")) < POINTER_MAX_CHARS and "15" in sections:
        chosen.append("15")
    return "\n\n".join(sections[item] for item in chosen), True