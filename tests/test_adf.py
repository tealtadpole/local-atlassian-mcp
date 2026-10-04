from jira_mcp.adf import render_adf


def test_none_is_empty():
    assert render_adf(None) == ""


def test_plain_string_passthrough():
    assert render_adf("already text") == "already text"


def test_paragraph_and_text():
    doc = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]},
    ]}
    assert render_adf(doc) == "Hello world"


def test_heading_and_list():
    doc = {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Steps"}]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "first"}]}]}
            ,
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "second"}]}]},
        ]},
    ]}
    text = render_adf(doc)
    assert "## Steps" in text
    assert "- first" in text
    assert "- second" in text


def test_mention_and_hard_break():
    doc = {"type": "doc", "content": [
        {"type": "paragraph", "content": [
            {"type": "mention", "attrs": {"text": "@Ann"}},
            {"type": "hardBreak"},
            {"type": "text", "text": "done"},
        ]},
    ]}
    text = render_adf(doc)
    assert "@Ann" in text
    assert "done" in text
