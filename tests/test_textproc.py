from atlassian_mcp.textproc import storage_to_text


def test_paragraph():
    assert storage_to_text("<p>Hello world</p>") == "Hello world"


def test_heading_and_list():
    xhtml = "<h2>Steps</h2><ul><li>first</li><li>second</li></ul>"
    text = storage_to_text(xhtml)
    assert "## Steps" in text
    assert "- first" in text
    assert "- second" in text


def test_table_cells():
    xhtml = "<table><tr><td>a</td><td>b</td></tr></table>"
    assert "a | b" in storage_to_text(xhtml)


def test_skips_style_and_script():
    xhtml = "<p>keep</p><style>.x{color:red}</style><script>alert(1)</script>"
    text = storage_to_text(xhtml)
    assert "keep" in text
    assert "color" not in text and "alert" not in text
