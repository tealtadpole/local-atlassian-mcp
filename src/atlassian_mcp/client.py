"""Read-only clients for the Jira Cloud and Confluence Cloud REST APIs.

Both products live on the same Atlassian Cloud site and share the same auth (account
email + API token, Basic Auth), so one `_BaseClient` handles requests/retries/auth and
`JiraClient` / `ConfluenceClient` add their product-specific endpoints.

Jira uses the current REST API v3, including the enhanced JQL search endpoint
(`/rest/api/3/search/jql`) that replaced the deprecated `/rest/api/3/search`.

Confluence Cloud still serves full-text/CQL search and content under the legacy
`/wiki/rest/api/*` namespace (same shape as Confluence Server/Data Center: CQL queries,
storage-format XHTML bodies), which is why `textproc.py` -- not `adf.py` -- renders
Confluence page bodies.
"""

from __future__ import annotations

import logging
import time
from email.utils import parsedate_to_datetime

import requests

from .config import AtlassianConfig

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 502, 503, 504}


class AtlassianError(Exception):
    pass


class AtlassianAuthError(AtlassianError):
    """The credentials were rejected: wrong email/API token, or the token was revoked."""


class _BaseClient:
    def __init__(self, cfg: AtlassianConfig, session: requests.Session | None = None):
        self.cfg = cfg
        self.base = cfg.base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.auth = (cfg.email, cfg.token)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self.session.verify = cfg.verify_ssl

    def _get(self, url: str, params: dict | None = None) -> dict:
        return self._request("GET", url, params=params)

    def _post(self, url: str, json: dict) -> dict:
        return self._request("POST", url, json=json)

    def _request(self, method: str, url: str, **kwargs) -> dict:
        attempts = self.cfg.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                r = self.session.request(method, url, timeout=self.cfg.timeout_seconds, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == attempts:
                    raise AtlassianError(f"Network error talking to Atlassian: {e}") from e
                self._backoff(attempt, None, f"network error ({type(e).__name__})")
                continue

            if r.status_code == 401:
                raise AtlassianAuthError(
                    "Atlassian rejected the credentials (HTTP 401). Check atlassian.email and the "
                    "API token: create a new one at "
                    "https://id.atlassian.com/manage-profile/security/api-tokens"
                )
            if r.status_code in RETRY_STATUSES or r.status_code >= 500:
                if attempt == attempts:
                    raise _http_error(r)
                self._backoff(attempt, r.headers.get("Retry-After"), f"HTTP {r.status_code}")
                continue
            if r.status_code >= 400:
                raise _http_error(r)

            if not r.content:
                return {}
            if "json" not in r.headers.get("Content-Type", ""):
                raise AtlassianError(
                    f"Expected JSON from {r.url} but got {r.headers.get('Content-Type')!r}. "
                    "Check base_url, or whether an SSO login page or proxy is intercepting requests."
                )
            return r.json()
        raise AssertionError("unreachable")

    def _backoff(self, attempt: int, retry_after: str | None, reason: str) -> None:
        delay = _retry_after_seconds(retry_after)
        if delay is None:
            delay = min(60, 2 ** attempt)
        log.warning("Atlassian %s; retrying in %.0fs (attempt %d/%d)",
                    reason, delay, attempt, self.cfg.max_retries)
        time.sleep(delay)


class JiraClient(_BaseClient):
    def myself(self) -> dict:
        return self._get(self.base + "/rest/api/3/myself")

    def list_projects(self) -> list[dict]:
        out: list[dict] = []
        start = 0
        while True:
            data = self._get(self.base + "/rest/api/3/project/search", {"startAt": start, "maxResults": 100})
            out.extend(data.get("values", []))
            if data.get("isLast", True):
                return out
            start += len(data.get("values", []))
            time.sleep(self.cfg.request_delay_seconds)

    def search(self, jql: str, max_results: int, fields: tuple[str, ...]) -> list[dict]:
        body = {"jql": jql, "maxResults": max_results, "fields": list(fields)}
        data = self._post(self.base + "/rest/api/3/search/jql", body)
        return data.get("issues", [])

    def get_issue(self, key: str, fields: tuple[str, ...]) -> dict | None:
        try:
            return self._get(f"{self.base}/rest/api/3/issue/{key}", {"fields": ",".join(fields)})
        except AtlassianError as e:
            if getattr(e, "status", None) in (403, 404):
                return None
            raise

    def get_comments(self, key: str, max_results: int) -> list[dict]:
        try:
            data = self._get(f"{self.base}/rest/api/3/issue/{key}/comment",
                             {"maxResults": max_results, "orderBy": "-created"})
        except AtlassianError as e:
            if getattr(e, "status", None) in (403, 404):
                return []
            raise
        return data.get("comments", [])


CONTENT_EXPAND = "body.storage,version,ancestors,space"


class ConfluenceClient(_BaseClient):
    def list_spaces(self) -> list[dict]:
        return list(self._paginate("/wiki/rest/api/space", {"limit": 100}))

    def search(self, cql: str, max_results: int) -> list[dict]:
        params = {"cql": cql, "limit": max_results, "expand": CONTENT_EXPAND}
        data = self._get(self.base + "/wiki/rest/api/content/search", params)
        return data.get("results", [])

    def get_page(self, page_id: str) -> dict | None:
        try:
            return self._get(f"{self.base}/wiki/rest/api/content/{page_id}", {"expand": CONTENT_EXPAND})
        except AtlassianError as e:
            if getattr(e, "status", None) in (403, 404):
                return None
            raise

    def _paginate(self, path: str, params: dict):
        url: str | None = self.base + path
        while url:
            data = self._get(url, params)
            yield from data.get("results", [])
            nxt = data.get("_links", {}).get("next")
            if not nxt:
                return
            url = nxt if nxt.startswith("http") else self.base + nxt
            params = None
            time.sleep(self.cfg.request_delay_seconds)


def _http_error(r: requests.Response) -> AtlassianError:
    snippet = r.text[:300].replace("\n", " ")
    err = AtlassianError(f"Atlassian returned HTTP {r.status_code} for {r.url}: {snippet}")
    err.status = r.status_code
    return err


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError):
        return None
