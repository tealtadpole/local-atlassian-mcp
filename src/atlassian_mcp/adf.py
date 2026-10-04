"""Render Atlassian Document Format (ADF) to plain text.

ADF is the rich-text JSON Jira Cloud uses for issue descriptions and comments, e.g.
{"type": "doc", "version": 1, "content": [...]}. This is a readable, not pixel-perfect,
text rendering: enough for an LLM to use the content, not to reconstruct the original.
"""

from __future__ import annotations

_BLOCK = {"paragraph", "heading", "codeBlock", "blockquote", "rule", "bulletList",
          "orderedList", "panel", "table"}


def render_adf(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):   # some fields/instances hand back plain text instead
        return value.strip()
    return _node(value).strip()


def _node(node: dict) -> str:
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t == "hardBreak":
        return "\n"
    if t == "rule":
        return "\n---\n"
    if t == "mention":
        return "@" + (node.get("attrs", {}).get("text") or "").lstrip("@")
    if t == "emoji":
        attrs = node.get("attrs", {})
        return attrs.get("text") or f":{attrs.get('shortName', '')}:"
    if t in ("inlineCard", "blockCard"):
        return node.get("attrs", {}).get("url", "")

    children = "".join(_node(c) for c in node.get("content", []))
    if t == "heading":
        level = node.get("attrs", {}).get("level", 1)
        return f"\n{'#' * level} {children}\n"
    if t == "listItem":
        return f"- {children.strip()}\n"
    if t == "codeBlock":
        return f"\n```\n{children}\n```\n"
    if t == "blockquote":
        return f"\n> {children.strip()}\n"
    if t in ("tableCell", "tableHeader"):
        return f"{children.strip()} | "
    if t == "tableRow":
        return f"{children}\n"
    if t in _BLOCK:
        return f"{children}\n"
    return children
