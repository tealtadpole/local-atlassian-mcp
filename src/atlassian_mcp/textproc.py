"""Turn Confluence storage-format XHTML into readable plain text.

Confluence Cloud's content/search API still returns bodies in the same storage format
as Server/Data Center (unlike Jira, which moved to Atlassian Document Format), so this
is the same walk `local-confluence-RAG` uses, minus the chunking it needs for its RAG
index -- this server reads pages live, so a full-page text is all a tool call needs.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

HEADINGS = {f"h{i}": i for i in range(1, 7)}
BLOCKS = {
    "p", "div", "pre", "blockquote", "table", "tr", "ul", "ol", "br", "hr",
    "ac:layout-section", "ac:layout-cell", "ac:task", "ac:rich-text-body", "ac:plain-text-body",
}
SKIP = {"ac:parameter", "ac:image", "ri:attachment", "ri:user", "ac:task-id", "ac:task-status",
        "style", "script"}
HEADING_MARK = "\x00"


def storage_to_text(xhtml: str) -> str:
    """Readable text with Markdown-style '#' headings, '- ' list items and '|' table cells."""
    soup = BeautifulSoup(xhtml, "html.parser")
    out: list[str] = []
    _walk(soup, out)
    lines = []
    for line in "".join(out).split("\n"):
        line = re.sub(r"[ \t ]+", " ", line).strip()
        if line.startswith(HEADING_MARK):
            line = line.lstrip(HEADING_MARK)
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"(\| ?){2,}", "| ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _walk(node: Tag, out: list[str]) -> None:
    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            out.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        if name in SKIP:
            continue
        if name in HEADINGS:
            title = child.get_text(" ", strip=True)
            if title:
                out.append(f"\n\n{HEADING_MARK}{'#' * HEADINGS[name]} {title}\n")
            continue
        if name == "ri:page":
            out.append(child.get("ri:content-title", ""))
            continue
        if name == "li":
            out.append("\n- ")
        elif name in ("td", "th"):
            out.append(" | ")
        elif name in BLOCKS:
            out.append("\n")
        _walk(child, out)
        if name in BLOCKS or name == "li":
            out.append("\n")
