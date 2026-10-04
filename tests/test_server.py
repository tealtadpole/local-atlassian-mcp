from atlassian_mcp.server import (
    build_confluence_cql,
    format_confluence_page,
    format_confluence_search_results,
    format_jira_issue,
    format_jira_search_results,
    scope_cql,
    scope_jql,
)


def test_scope_jql_empty_projects_passthrough():
    assert scope_jql("status = Open", ()) == "status = Open"


def test_scope_jql_wraps_with_project_filter():
    assert scope_jql("status = Open", ("ENG", "OPS")) == "project in (ENG, OPS) AND (status = Open)"


def test_scope_cql_wraps_with_space_filter():
    cql = scope_cql('text ~ "vpn"', ("ENG",))
    assert cql == 'space in ("ENG") AND (text ~ "vpn")'


def test_build_confluence_cql_with_space():
    cql = build_confluence_cql("vpn access", "ENG")
    assert cql == 'space = "ENG" AND type = page AND text ~ "vpn access"'


def test_build_confluence_cql_escapes_quotes():
    cql = build_confluence_cql('say "hi"', None)
    assert '\\"hi\\"' in cql


def test_format_jira_search_results():
    issues = [{"key": "ENG-1", "fields": {
        "summary": "Fix the thing", "status": {"name": "Open"},
        "assignee": {"displayName": "Bob"}, "updated": "2026-10-01T00:00:00.000+0000"}}]
    out = format_jira_search_results(issues, "https://corp.atlassian.net")
    assert "ENG-1: Fix the thing" in out
    assert "https://corp.atlassian.net/browse/ENG-1" in out


def test_format_jira_issue_with_comments():
    issue = {"key": "ENG-1", "fields": {
        "summary": "Fix the thing", "status": {"name": "Open"}, "assignee": {"displayName": "Bob"},
        "reporter": {"displayName": "Ann"}, "issuetype": {"name": "Bug"}, "priority": {"name": "High"},
        "labels": ["urgent"], "created": "2026-09-01T00:00:00.000+0000",
        "updated": "2026-10-01T00:00:00.000+0000",
        "description": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Steps to repro"}]}]},
    }}
    comments = [{"author": {"displayName": "Ann"}, "created": "2026-09-02T00:00:00.000+0000",
                "body": {"type": "doc", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "Still happening"}]}]}}]
    out = format_jira_issue(issue, comments, "https://corp.atlassian.net")
    assert "Steps to repro" in out
    assert "Ann (2026-09-02): Still happening" in out


def test_format_confluence_search_results():
    pages = [{"id": "1", "title": "VPN setup", "space": {"key": "ENG"},
             "version": {"when": "2026-09-30T12:00:00.000Z"},
             "_links": {"webui": "/wiki/spaces/ENG/pages/1"}}]
    out = format_confluence_search_results(pages, "https://corp.atlassian.net")
    assert "VPN setup" in out
    assert "page_id: 1" in out
    assert "https://corp.atlassian.net/wiki/spaces/ENG/pages/1" in out


def test_format_confluence_page():
    page = {"title": "VPN setup", "space": {"key": "ENG", "name": "Engineering"},
            "version": {"number": 3, "when": "2026-09-30T12:00:00.000Z"},
            "_links": {"webui": "/wiki/spaces/ENG/pages/1"},
            "body": {"storage": {"value": "<p>Request access via the portal.</p>"}}}
    out = format_confluence_page(page, "https://corp.atlassian.net")
    assert "VPN setup  (space: Engineering)" in out
    assert "version 3" in out
    assert "Request access via the portal." in out
