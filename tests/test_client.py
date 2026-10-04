import pytest

from atlassian_mcp.client import AtlassianAuthError, ConfluenceClient, JiraClient


def test_jira_search_returns_issues(fake, make_config):
    fake.add_issue("ENG-1", "Fix the thing", status="Open")
    fake.add_issue("ENG-2", "Another bug", status="Done")
    cfg = make_config(fake.start())
    client = JiraClient(cfg.atlassian)
    issues = client.search("project = ENG", 10, ("summary", "status"))
    assert {i["key"] for i in issues} == {"ENG-1", "ENG-2"}


def test_jira_get_issue_not_found_returns_none(fake, make_config):
    cfg = make_config(fake.start())
    client = JiraClient(cfg.atlassian)
    assert client.get_issue("ENG-999", ("summary",)) is None


def test_jira_get_issue_returns_fields(fake, make_config):
    fake.add_issue("ENG-1", "Fix the thing", assignee="Bob")
    cfg = make_config(fake.start())
    client = JiraClient(cfg.atlassian)
    issue = client.get_issue("ENG-1", ("summary", "assignee"))
    assert issue["fields"]["summary"] == "Fix the thing"
    assert issue["fields"]["assignee"]["displayName"] == "Bob"


def test_jira_comments_empty_for_missing_issue(fake, make_config):
    cfg = make_config(fake.start())
    client = JiraClient(cfg.atlassian)
    assert client.get_comments("ENG-999", 20) == []


def test_jira_list_projects(fake, make_config):
    cfg = make_config(fake.start())
    client = JiraClient(cfg.atlassian)
    assert [p["key"] for p in client.list_projects()] == ["ENG", "OPS"]


def test_confluence_search_matches_text(fake, make_config):
    fake.add_page("1", "ENG", "VPN setup", "<p>how to request VPN access</p>")
    fake.add_page("2", "HR", "Onboarding", "<p>welcome to the company</p>")
    cfg = make_config(fake.start())
    client = ConfluenceClient(cfg.atlassian)
    pages = client.search('type = page AND text ~ "VPN"', 10)
    assert [p["id"] for p in pages] == ["1"]


def test_confluence_get_page_not_found_returns_none(fake, make_config):
    cfg = make_config(fake.start())
    client = ConfluenceClient(cfg.atlassian)
    assert client.get_page("999") is None


def test_confluence_get_page_returns_body(fake, make_config):
    fake.add_page("1", "ENG", "VPN setup", "<p>how to request VPN access</p>")
    cfg = make_config(fake.start())
    client = ConfluenceClient(cfg.atlassian)
    page = client.get_page("1")
    assert page["title"] == "VPN setup"
    assert "VPN access" in page["body"]["storage"]["value"]


def test_confluence_list_spaces(fake, make_config):
    cfg = make_config(fake.start())
    client = ConfluenceClient(cfg.atlassian)
    assert {s["key"] for s in client.list_spaces()} == {"ENG", "HR"}


def test_wrong_credentials_raise_auth_error(fake, make_config):
    cfg = make_config(fake.start())
    client = JiraClient(cfg.atlassian)
    client.session.auth = ("wrong@example.com", "wrong-token")
    with pytest.raises(AtlassianAuthError):
        client.myself()
