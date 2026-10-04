"""A tiny stand-in for the Jira Cloud + Confluence Cloud REST APIs, served over real HTTP."""

from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

EMAIL = "tester@example.com"
TOKEN = "test-token"


@dataclass
class FakeIssue:
    key: str
    summary: str
    status: str = "Open"
    assignee: str | None = "Ann Reporter"
    description: dict | str | None = None
    comments: list[dict] = field(default_factory=list)


@dataclass
class FakePage:
    id: str
    space: str
    title: str
    body: str
    version: int = 1


@dataclass
class FakeAtlassian:
    issues: dict[str, FakeIssue] = field(default_factory=dict)
    projects: list[str] = field(default_factory=list)
    pages: dict[str, FakePage] = field(default_factory=dict)
    spaces: dict[str, str] = field(default_factory=dict)   # key -> name
    requests: list[str] = field(default_factory=list)

    def add_issue(self, key, summary, **kwargs):
        self.issues[key] = FakeIssue(key, summary, **kwargs)

    def add_page(self, id, space, title, body, version=1):
        self.pages[id] = FakePage(id, space, title, body, version)

    # ---- HTTP plumbing ------------------------------------------------------

    def start(self) -> str:
        fake = self
        expected_auth = "Basic " + base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def _handle(self, method):
                url = urlparse(self.path)
                fake.requests.append(self.path)
                if self.headers.get("Authorization") != expected_auth:
                    return self._send(401, {"message": "unauthorized"})
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                status, resp = fake.route(method, url.path, q, body)
                self._send(status, resp)

            def _send(self, status, body, headers=None):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def stop(self):
        if hasattr(self, "httpd"):
            self.httpd.shutdown()

    # ---- Jira -----------------------------------------------------------------

    def route(self, method, path, q, body):
        if path == "/rest/api/3/myself":
            return 200, {"displayName": "Test User", "emailAddress": EMAIL}
        if path == "/rest/api/3/project/search":
            return 200, {"values": [{"key": p} for p in self.projects], "isLast": True}
        if path == "/rest/api/3/search/jql" and method == "POST":
            matches = [self._issue_json(i, body.get("fields", [])) for i in self.issues.values()]
            return 200, {"issues": matches, "isLast": True}
        if path.startswith("/rest/api/3/issue/") and path.endswith("/comment"):
            key = path.split("/")[-2]
            issue = self.issues.get(key)
            if issue is None:
                return 404, {"errorMessages": ["Issue does not exist"]}
            return 200, {"comments": issue.comments}
        if path.startswith("/rest/api/3/issue/"):
            key = path.rsplit("/", 1)[-1]
            issue = self.issues.get(key)
            if issue is None:
                return 404, {"errorMessages": ["Issue does not exist"]}
            fields = (q.get("fields") or "").split(",") if q.get("fields") else None
            return 200, self._issue_json(issue, fields)

        if path == "/wiki/rest/api/space":
            items = [{"key": k, "name": n} for k, n in sorted(self.spaces.items())]
            return 200, {"results": items, "_links": {}}
        if path == "/wiki/rest/api/content/search":
            cql = q.get("cql", "")
            items = [self._page_json(p) for p in self.pages.values() if self._matches(p, cql)]
            return 200, {"results": items}
        if path.startswith("/wiki/rest/api/content/"):
            page = self.pages.get(path.rsplit("/", 1)[-1])
            if page is None:
                return 404, {"message": "not found"}
            return 200, self._page_json(page)
        return 404, {"errorMessages": [f"unknown path {path}"]}

    def _issue_json(self, issue: FakeIssue, fields: list[str] | None) -> dict:
        all_fields = {
            "summary": issue.summary,
            "status": {"name": issue.status},
            "assignee": {"displayName": issue.assignee} if issue.assignee else None,
            "description": issue.description,
        }
        chosen = {k: v for k, v in all_fields.items() if not fields or k in fields}
        return {"key": issue.key, "fields": chosen}

    def _page_json(self, p: FakePage) -> dict:
        return {
            "id": p.id, "title": p.title,
            "space": {"key": p.space, "name": self.spaces.get(p.space, p.space)},
            "version": {"number": p.version, "when": "2026-09-30T12:00:00.000Z"},
            "body": {"storage": {"value": p.body, "representation": "storage"}},
            "_links": {"webui": f"/wiki/spaces/{p.space}/pages/{p.id}"},
        }

    @staticmethod
    def _matches(page: FakePage, cql: str) -> bool:
        # Good enough for tests: pull the quoted text term and the optional space filter out.
        import re

        space_match = re.search(r'space\s*=\s*"([^"]+)"', cql)
        if space_match and space_match.group(1) != page.space:
            return False
        space_in = re.search(r"space in \(([^)]*)\)", cql)
        if space_in:
            allowed = {s.strip().strip('"') for s in space_in.group(1).split(",")}
            if page.space not in allowed:
                return False
        text_match = re.search(r'text ~ "([^"]*)"', cql)
        if text_match and text_match.group(1).lower() not in page.title.lower() + page.body.lower():
            return False
        return True
