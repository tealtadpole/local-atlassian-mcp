# jira-mcp

Read-only access to **Jira Cloud**, served to Claude Code (or any MCP client) as a local
**stdio MCP server**. No local index: searches run live against Jira via JQL.

```
Jira Cloud REST API v3 ──(email + API token, read-only)──► jira-mcp serve ──► Claude Code / agent-harness
                                                                (stdio / MCP)
```

Everything runs on your machine; nothing is cached or stored outside Jira itself. Text the MCP
tools return does go to the model provider as part of your conversation.

## Requirements

| What | Details |
|---|---|
| **OS** | Linux or macOS. On Windows, use WSL. |
| **Python** | 3.11 or newer (uses the built-in `tomllib`). On Debian/Ubuntu also install `python3-venv`. |
| **Jira** | **Jira Cloud** (an `*.atlassian.net` site). Not Jira Server/Data Center (see Limitations). |
| **API token** | Atlassian account → [API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → *Create API token*. Paired with the account's email for Basic Auth. |
| **Network** | HTTPS access to your Jira Cloud site and `api.atlassian.com`. |
| **Claude Code** | Optional. Any MCP client that can launch a stdio server works; the CLI also works on its own. |

Python packages (installed by `pip` below): `mcp` 2.x, `requests`.

## Installation

```bash
git clone https://github.com/tealtadpole/local-jira-mcp.git
cd local-jira-mcp
python3 -m venv .venv
.venv/bin/pip install -e .              # add ".[dev]" to also install pytest

cp config.example.toml config.toml      # gitignored
chmod 600 config.toml
$EDITOR config.toml                     # at least base_url and email
export JIRA_API_TOKEN='...'             # or set token = "..." in config.toml
```

Then:

```bash
.venv/bin/jira-mcp check                      # tests the URL + credentials, lists accessible projects
.venv/bin/jira-mcp search "project = ENG AND status = \"In Progress\""
.venv/bin/jira-mcp get ENG-123
```

**Common problems**

| Symptom | Fix |
|---|---|
| `HTTP 401 ...` | Wrong `email`/`JIRA_API_TOKEN`, or the token was revoked: create a new one. |
| `Expected JSON ... got 'text/html'` | `base_url` is wrong or an SSO page/proxy is intercepting. |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Corporate TLS inspection: set `verify_ssl = "/path/to/corp-ca.pem"`. |
| `No module named 'tomllib'` | Python is older than 3.11. |

## Use it from Claude Code

Run this from the repository folder (`$PWD` becomes the absolute path):

```bash
claude mcp add -s user jira \
  -e JIRA_API_TOKEN="$JIRA_API_TOKEN" \
  -- "$PWD/.venv/bin/jira-mcp" --config "$PWD/config.toml" serve
```

`-e` stores the token in Claude Code's MCP config (`~/.claude.json`). If you'd rather keep it
only in `config.toml`, leave out `-e`. Restart Claude Code, then check `/mcp`. Tools:

| Tool | What it does |
|---|---|
| `search_jira(jql, max_results?)` | Runs a JQL query, returns matching issues: key, summary, status, assignee, URL |
| `get_jira_issue(issue_key, include_comments?)` | Full issue: description and metadata, plus recent comments |

To allow the read-only tools without permission prompts, add them to `permissions.allow` in
`~/.claude/settings.json`, e.g. `"mcp__jira__search_jira"`.

## Use it from agent-harness

Add it as another `[mcp.servers.<name>]` entry in agent-harness's `config.toml`, alongside any
other MCP tools (e.g. `local-confluence-RAG`):

```toml
[mcp.servers.jira]
command = "/abs/path/local-jira-mcp/.venv/bin/jira-mcp"
args = ["--config", "/abs/path/local-jira-mcp/config.toml", "serve"]
env = { JIRA_API_TOKEN = "${JIRA_API_TOKEN}" }
tools = ["search_jira", "get_jira_issue"]
```

## Security notes

- **Your token sees what you see.** Searches run with your Jira permissions; don't share the
  server or expose it to other people.
- Keep the token out of files where you can (`token_env`). If it's in `config.toml`, the tool
  warns unless the file is `chmod 600`. It's never written to logs.
- Tool output is labelled as reference data, not instructions. Issues and comments are editable
  by many people and could contain prompt-injection text.
- The optional `jira.projects` allow-list scopes every search even if the token itself can see
  more projects — a defense-in-depth restriction, not a substitute for Jira's own permissions.
- Behind a corporate TLS proxy, set `verify_ssl = "/path/to/corp-ca.pem"`.

## Limitations

- **Jira Cloud only** (email + API token, Basic Auth, REST v3). Jira Server/Data Center uses a
  Bearer PAT and a different REST version; it would need a different client in `client.py`.
- Read-only: search and read issues/comments. No create, update, transition or delete tools.
- Uses the newer `/rest/api/3/search/jql` endpoint (the deprecated `/rest/api/3/search` is not
  used). If Atlassian changes that endpoint's shape again, update `client.py`.
- Issue descriptions/comments are Atlassian Document Format (ADF); `adf.py` renders them to
  readable plain text, not a pixel-perfect reconstruction. Attachments and embedded media aren't
  fetched.

## Layout

```
src/jira_mcp/
  config.py   load + validate config.toml, resolve the token
  client.py   read-only REST client: auth, retries, 429/5xx handling, the JQL search endpoint
  adf.py      Atlassian Document Format (ADF) -> plain text
  server.py   MCP tools (search_jira, get_jira_issue) + result formatting
  cli.py      check / search / get / serve
tests/        runs against a fake Jira Cloud HTTP server (`.venv/bin/pytest`)
```

## License

[MIT](LICENSE). Not affiliated with or endorsed by Atlassian. "Jira" is a trademark of Atlassian.
