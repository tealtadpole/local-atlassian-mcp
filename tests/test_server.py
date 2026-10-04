from jira_mcp.server import format_issue, format_search_results, scope_jql


def test_scope_jql_empty_projects_passthrough():
    assert scope_jql("status = Open", ()) == "status = Open"


def test_scope_jql_wraps_with_project_filter():
    jql = scope_jql("status = Open", ("ENG", "OPS"))
    assert jql == "project in (ENG, OPS) AND (status = Open)"


def test_format_search_results():
    issues = [{"key": "ENG-1", "fields": {
        "summary": "Fix the thing", "status": {"name": "Open"},
        "assignee": {"displayName": "Bob"}, "updated": "2026-10-01T00:00:00.000+0000"}}]
    out = format_search_results(issues, "https://corp.atlassian.net")
    assert "ENG-1: Fix the thing" in out
    assert "Status: Open" in out
    assert "https://corp.atlassian.net/browse/ENG-1" in out


def test_format_search_results_unassigned():
    issues = [{"key": "ENG-2", "fields": {"summary": "x", "status": {}, "assignee": None}}]
    assert "Unassigned" in format_search_results(issues, "https://corp.atlassian.net")


def test_format_issue_with_comments():
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
    out = format_issue(issue, comments, "https://corp.atlassian.net")
    assert "ENG-1: Fix the thing" in out
    assert "Steps to repro" in out
    assert "Ann (2026-09-02): Still happening" in out
    assert "Labels: urgent" in out
