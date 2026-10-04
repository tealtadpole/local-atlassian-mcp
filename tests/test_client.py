import pytest

from jira_mcp.client import JiraAuthError, JiraClient, JiraError


def test_search_returns_issues(fake, make_config):
    fake.add("ENG-1", "Fix the thing", status="Open")
    fake.add("ENG-2", "Another bug", status="Done")
    cfg = make_config(fake.start())
    client = JiraClient(cfg.jira)
    issues = client.search("project = ENG", 10, ("summary", "status"))
    assert {i["key"] for i in issues} == {"ENG-1", "ENG-2"}


def test_get_issue_not_found_returns_none(fake, make_config):
    cfg = make_config(fake.start())
    client = JiraClient(cfg.jira)
    assert client.get_issue("ENG-999", ("summary",)) is None


def test_get_issue_returns_fields(fake, make_config):
    fake.add("ENG-1", "Fix the thing", assignee="Bob")
    cfg = make_config(fake.start())
    client = JiraClient(cfg.jira)
    issue = client.get_issue("ENG-1", ("summary", "assignee"))
    assert issue["fields"]["summary"] == "Fix the thing"
    assert issue["fields"]["assignee"]["displayName"] == "Bob"


def test_comments_empty_for_missing_issue(fake, make_config):
    cfg = make_config(fake.start())
    client = JiraClient(cfg.jira)
    assert client.get_comments("ENG-999", 20) == []


def test_wrong_credentials_raise_auth_error(fake, make_config, monkeypatch):
    cfg = make_config(fake.start())
    client = JiraClient(cfg.jira)
    client.session.auth = ("wrong@example.com", "wrong-token")
    with pytest.raises(JiraAuthError):
        client.myself()


def test_list_projects(fake, make_config):
    cfg = make_config(fake.start())
    client = JiraClient(cfg.jira)
    assert [p["key"] for p in client.list_projects()] == ["ENG", "OPS"]
