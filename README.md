# atlassian-mcp

Read-only access to **Jira Cloud** and **Confluence Cloud**, served to Claude Code (or any MCP
client) as a local **stdio MCP server**. No local index: both products are searched live.

```
Jira Cloud REST API v3        ──┐
(JQL search, issues+comments)   │  (same site, same email + API token)
                                 ├──► atlassian-mcp serve ──► Claude Code / agent-harness
Confluence Cloud REST API       │        (stdio / MCP)
(CQL search, pages)           ──┘
```

Everything runs on your machine; nothing is cached or stored outside Jira/Confluence
themselves. Text the MCP tools return does go to the model provider as part of your conversation.

## Requirements

| What | Details |
|---|---|
| **OS** | Linux or macOS. On Windows, use WSL. |
| **Python** | 3.11 or newer (uses the built-in `tomllib`). On Debian/Ubuntu also install `python3-venv`. |
| **Atlassian site** | **Cloud** (an `*.atlassian.net` site) with Jira and/or Confluence. Not Server/Data Center (see Limitations). |
| **API token** | Atlassian account → [API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → *Create API token*. Paired with the account's email for Basic Auth; works for both Jira and Confluence on the same site. |
| **Network** | HTTPS access to your Atlassian Cloud site. |
| **Claude Code** | Optional. Any MCP client that can launch a stdio server works; the CLI also works on its own. |

Python packages (installed by `pip` below): `mcp` 2.x, `requests`, `beautifulsoup4`.

## Installation

```bash
git clone https://github.com/tealtadpole/local-atlassian-mcp.git
cd local-atlassian-mcp
python3 -m venv .venv
.venv/bin/pip install -e .              # add ".[dev]" to also install pytest

cp config.example.toml config.toml      # gitignored
chmod 600 config.toml
$EDITOR config.toml                     # at least base_url and email
export ATLASSIAN_API_TOKEN='...'        # or set token = "..." in config.toml
```

Then:

```bash
.venv/bin/atlassian-mcp check                        # tests credentials, lists projects + spaces
.venv/bin/atlassian-mcp jira-search 'project = ENG AND status = "In Progress"'
.venv/bin/atlassian-mcp jira-get ENG-123
.venv/bin/atlassian-mcp confluence-search "how do I request VPN access"
.venv/bin/atlassian-mcp confluence-get 12345
```

If you only use one of the two products, set `enabled = false` under `[jira]` or
`[confluence]` in `config.toml` and that product's tools won't be registered at all.

**Common problems**

| Symptom | Fix |
|---|---|
| `HTTP 401 ...` | Wrong `email`/`ATLASSIAN_API_TOKEN`, or the token was revoked: create a new one. |
| `Expected JSON ... got 'text/html'` | `base_url` is wrong or an SSO page/proxy is intercepting. |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Corporate TLS inspection: set `verify_ssl = "/path/to/corp-ca.pem"`. |
| `No module named 'tomllib'` | Python is older than 3.11. |

## Use it from Claude Code

Run this from the repository folder (`$PWD` becomes the absolute path):

```bash
claude mcp add -s user atlassian \
  -e ATLASSIAN_API_TOKEN="$ATLASSIAN_API_TOKEN" \
  -- "$PWD/.venv/bin/atlassian-mcp" --config "$PWD/config.toml" serve
```

`-e` stores the token in Claude Code's MCP config (`~/.claude.json`). If you'd rather keep it
only in `config.toml`, leave out `-e`. Restart Claude Code, then check `/mcp`. Tools:

| Tool | What it does |
|---|---|
| `search_jira(jql, max_results?)` | Runs a JQL query, returns matching issues: key, summary, status, assignee, URL |
| `get_jira_issue(issue_key, include_comments?)` | Full issue: description and metadata, plus recent comments |
| `search_confluence(query, max_results?, space?)` | Keyword (CQL) search, returns matching pages: title, space, URL, page_id |
| `get_confluence_page(page_id)` | Full text of one Confluence page |

To allow the read-only tools without permission prompts, add them to `permissions.allow` in
`~/.claude/settings.json`, e.g. `"mcp__atlassian__search_jira"`.

## Use it from agent-harness

Add it as another `[mcp.servers.<name>]` entry in agent-harness's `config.toml`:

```toml
[mcp.servers.atlassian]
command = "/abs/path/local-atlassian-mcp/.venv/bin/atlassian-mcp"
args = ["--config", "/abs/path/local-atlassian-mcp/config.toml", "serve"]
env = { ATLASSIAN_API_TOKEN = "${ATLASSIAN_API_TOKEN}" }
tools = ["search_jira", "get_jira_issue", "search_confluence", "get_confluence_page"]
```

> **Don't run this alongside `local-confluence-RAG`'s Confluence tools at the same time.**
> agent-harness doesn't namespace MCP tool names by server, and both expose tools named
> `search_confluence` / `get_confluence_page`. Use this one for Confluence **Cloud**, use
> `local-confluence-RAG` for Confluence **Server/Data Center** — not both.

## Security notes

- **Your token sees what you see.** Searches run with your Atlassian permissions; don't share
  the server or expose it to other people.
- Keep the token out of files where you can (`token_env`). If it's in `config.toml`, the tool
  warns unless the file is `chmod 600`. It's never written to logs.
- Tool output is labelled as reference data, not instructions. Issues, comments and wiki pages
  are editable by many people and could contain prompt-injection text.
- The optional `jira.projects` / `confluence.spaces` allow-lists scope every search even if the
  token itself can see more — defense-in-depth, not a substitute for Atlassian's own permissions.
- Behind a corporate TLS proxy, set `verify_ssl = "/path/to/corp-ca.pem"`.

## Limitations

- **Cloud only** (email + API token, Basic Auth). Jira/Confluence Server or Data Center use a
  Bearer PAT and different REST versions; they'd need a different client in `client.py`. For
  Confluence Server/DC, see [local-confluence-RAG](https://github.com/tealtadpole/local-confluence-RAG).
- Read-only: search and read issues/pages/comments. No create, update, transition or delete tools.
- Jira search uses the newer `/rest/api/3/search/jql` endpoint (the deprecated `/rest/api/3/search`
  is not used). If Atlassian changes that endpoint's shape again, update `client.py`.
- Jira issue text is Atlassian Document Format (ADF); `adf.py` renders it to readable plain text,
  not a pixel-perfect reconstruction. Confluence page bodies are still storage-format XHTML on
  Cloud, rendered by `textproc.py`. Attachments and embedded media aren't fetched either way.
- Confluence search has no local index (live CQL search only); fine for interactive use, not a
  substitute for `local-confluence-RAG`'s semantic search over a large wiki.

## Layout

```
src/atlassian_mcp/
  config.py    load + validate config.toml, resolve the token
  client.py    read-only REST clients: shared auth/retries, JiraClient, ConfluenceClient
  adf.py       Atlassian Document Format (Jira) -> plain text
  textproc.py  Confluence storage-format XHTML -> plain text
  server.py    MCP tools (search_jira, get_jira_issue, search_confluence, get_confluence_page)
  cli.py       check / jira-search / jira-get / confluence-search / confluence-get / serve
tests/         runs against a fake Jira+Confluence Cloud HTTP server (`.venv/bin/pytest`)
```

## License

[MIT](LICENSE). Not affiliated with or endorsed by Atlassian. "Jira" and "Confluence" are
trademarks of Atlassian.
