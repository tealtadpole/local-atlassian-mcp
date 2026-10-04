"""Command line: check, jira-search, jira-get, confluence-search, confluence-get, serve."""

from __future__ import annotations

import argparse
import logging
import sys

from .client import AtlassianError, ConfluenceClient, JiraClient
from .config import Config, ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlassian-mcp",
                                     description="Read-only Jira Cloud + Confluence Cloud access over MCP.")
    parser.add_argument("--config", help="path to config.toml (default: $ATLASSIAN_MCP_CONFIG, "
                                         "./config.toml, ~/.config/atlassian-mcp/config.toml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="test the URL and credentials; list accessible projects/spaces")
    p_js = sub.add_parser("jira-search", help="run a JQL search from the terminal")
    p_js.add_argument("jql")
    p_js.add_argument("-k", type=int, default=None, help="number of results")
    p_jg = sub.add_parser("jira-get", help="show one Jira issue (with comments)")
    p_jg.add_argument("key")
    p_cs = sub.add_parser("confluence-search", help="search Confluence from the terminal")
    p_cs.add_argument("query")
    p_cs.add_argument("-k", type=int, default=None, help="number of results")
    p_cs.add_argument("--space", help="only this space key")
    p_cg = sub.add_parser("confluence-get", help="show one Confluence page")
    p_cg.add_argument("page_id")
    sub.add_parser("serve", help="run the MCP server on stdio (what Claude Code / agent-harness launches)")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        cfg = load_config(args.config)
        return COMMANDS[args.command](cfg, args)
    except (ConfigError, AtlassianError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _check(cfg: Config, args) -> int:
    ok = True
    if cfg.jira.enabled:
        jira = JiraClient(cfg.atlassian)
        me = jira.myself()
        print(f"Jira: connected to {cfg.atlassian.base_url} as {me.get('displayName') or me.get('emailAddress')}")
        keys = [p["key"] for p in jira.list_projects()]
        print(f"  Accessible projects ({len(keys)}): {', '.join(keys) or 'none'}")
        if missing := [p for p in cfg.jira.projects if p not in keys]:
            print(f"  WARNING: jira.projects not visible to this token: {', '.join(missing)}")
    if cfg.confluence.enabled:
        confluence = ConfluenceClient(cfg.atlassian)
        spaces = confluence.list_spaces()
        keys = [s["key"] for s in spaces]
        print(f"Confluence: {len(keys)} accessible space(s): {', '.join(keys) or 'none'}")
        if missing := [s for s in cfg.confluence.spaces if s not in keys]:
            print(f"  WARNING: confluence.spaces not visible to this token: {', '.join(missing)}")
    return 0 if ok else 1


def _jira_search(cfg: Config, args) -> int:
    from .server import JIRA_SEARCH_FIELDS, format_jira_search_results, scope_jql

    client = JiraClient(cfg.atlassian)
    jql = scope_jql(args.jql, cfg.jira.projects)
    issues = client.search(jql, args.k or cfg.search.default_results, JIRA_SEARCH_FIELDS)
    print(format_jira_search_results(issues, cfg.atlassian.base_url) if issues else "No results.")
    return 0


def _jira_get(cfg: Config, args) -> int:
    from .server import JIRA_ISSUE_FIELDS, MAX_COMMENTS, format_jira_issue

    client = JiraClient(cfg.atlassian)
    issue = client.get_issue(args.key, JIRA_ISSUE_FIELDS)
    if issue is None:
        print(f"No issue {args.key} (not found, or you don't have access).")
        return 1
    comments = client.get_comments(args.key, MAX_COMMENTS)
    print(format_jira_issue(issue, comments, cfg.atlassian.base_url))
    return 0


def _confluence_search(cfg: Config, args) -> int:
    from .server import build_confluence_cql, format_confluence_search_results, scope_cql

    client = ConfluenceClient(cfg.atlassian)
    cql = scope_cql(build_confluence_cql(args.query, args.space), cfg.confluence.spaces)
    pages = client.search(cql, args.k or cfg.search.default_results)
    print(format_confluence_search_results(pages, cfg.atlassian.base_url) if pages else "No results.")
    return 0


def _confluence_get(cfg: Config, args) -> int:
    from .server import format_confluence_page

    client = ConfluenceClient(cfg.atlassian)
    page = client.get_page(args.page_id)
    if page is None:
        print(f"No page {args.page_id} (not found, or you don't have access).")
        return 1
    print(format_confluence_page(page, cfg.atlassian.base_url))
    return 0


def _serve(cfg: Config, args) -> int:
    from .server import serve

    serve(cfg)
    return 0


COMMANDS = {
    "check": _check,
    "jira-search": _jira_search,
    "jira-get": _jira_get,
    "confluence-search": _confluence_search,
    "confluence-get": _confluence_get,
    "serve": _serve,
}


def _setup_logging(verbose: bool) -> None:
    # stderr only: in `serve` mode stdout carries the MCP protocol.
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers[:] = [console]
    logging.getLogger("urllib3").setLevel(logging.WARNING)


if __name__ == "__main__":
    sys.exit(main())
