"""Command line: check, search, get, serve."""

from __future__ import annotations

import argparse
import logging
import sys

from .client import JiraClient, JiraError
from .config import Config, ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jira-mcp", description="Read-only Jira Cloud access over MCP.")
    parser.add_argument("--config", help="path to config.toml (default: $JIRA_MCP_CONFIG, "
                                         "./config.toml, ~/.config/jira-mcp/config.toml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="test the URL and credentials, and list accessible projects")
    p_search = sub.add_parser("search", help="run a JQL search from the terminal")
    p_search.add_argument("jql")
    p_search.add_argument("-k", type=int, default=None, help="number of results")
    p_get = sub.add_parser("get", help="show one issue (with comments)")
    p_get.add_argument("key")
    sub.add_parser("serve", help="run the MCP server on stdio (what Claude Code / agent-harness launches)")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        cfg = load_config(args.config)
        return COMMANDS[args.command](cfg, args)
    except (ConfigError, JiraError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _check(cfg: Config, args) -> int:
    client = JiraClient(cfg.jira)
    me = client.myself()
    print(f"Connected to {cfg.jira.base_url} as {me.get('displayName') or me.get('emailAddress')}")
    projects = client.list_projects()
    keys = [p["key"] for p in projects]
    print(f"Accessible projects ({len(keys)}): {', '.join(keys) or 'none'}")
    if missing := [p for p in cfg.jira.projects if p not in keys]:
        print(f"WARNING: jira.projects not visible to this token: {', '.join(missing)}")
    return 0


def _search(cfg: Config, args) -> int:
    from .server import SEARCH_FIELDS, format_search_results, scope_jql

    client = JiraClient(cfg.jira)
    jql = scope_jql(args.jql, cfg.jira.projects)
    issues = client.search(jql, args.k or cfg.search.default_results, SEARCH_FIELDS)
    print(format_search_results(issues, cfg.jira.base_url) if issues else "No results.")
    return 0


def _get(cfg: Config, args) -> int:
    from .server import ISSUE_FIELDS, MAX_COMMENTS, format_issue

    client = JiraClient(cfg.jira)
    issue = client.get_issue(args.key, ISSUE_FIELDS)
    if issue is None:
        print(f"No issue {args.key} (not found, or you don't have access).")
        return 1
    comments = client.get_comments(args.key, MAX_COMMENTS)
    print(format_issue(issue, comments, cfg.jira.base_url))
    return 0


def _serve(cfg: Config, args) -> int:
    from .server import serve

    serve(cfg)
    return 0


COMMANDS = {"check": _check, "search": _search, "get": _get, "serve": _serve}


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
