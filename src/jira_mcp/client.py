"""Read-only client for the Jira Cloud REST API (v3), including the enhanced JQL
search endpoint (`/search/jql`) that replaced the deprecated `/search`."""

from __future__ import annotations

import logging
import time
from email.utils import parsedate_to_datetime

import requests

from .config import JiraConfig

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 502, 503, 504}


class JiraError(Exception):
    pass


class JiraAuthError(JiraError):
    """The credentials were rejected: wrong email/API token, or the token was revoked."""


class JiraClient:
    def __init__(self, cfg: JiraConfig, session: requests.Session | None = None):
        self.cfg = cfg
        self.base = cfg.base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.auth = (cfg.email, cfg.token)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self.session.verify = cfg.verify_ssl

    # ---- public API -------------------------------------------------------

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
        except JiraError as e:
            if getattr(e, "status", None) in (403, 404):
                return None
            raise

    def get_comments(self, key: str, max_results: int) -> list[dict]:
        try:
            data = self._get(f"{self.base}/rest/api/3/issue/{key}/comment",
                             {"maxResults": max_results, "orderBy": "-created"})
        except JiraError as e:
            if getattr(e, "status", None) in (403, 404):
                return []
            raise
        return data.get("comments", [])

    # ---- internals --------------------------------------------------------

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
                    raise JiraError(f"Network error talking to Jira: {e}") from e
                self._backoff(attempt, None, f"network error ({type(e).__name__})")
                continue

            if r.status_code == 401:
                raise JiraAuthError(
                    "Jira rejected the credentials (HTTP 401). Check jira.email and the API "
                    "token: create a new one at https://id.atlassian.com/manage-profile/security/api-tokens"
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
                raise JiraError(
                    f"Expected JSON from {r.url} but got {r.headers.get('Content-Type')!r}. "
                    "Check base_url, or whether an SSO login page or proxy is intercepting requests."
                )
            return r.json()
        raise AssertionError("unreachable")

    def _backoff(self, attempt: int, retry_after: str | None, reason: str) -> None:
        delay = _retry_after_seconds(retry_after)
        if delay is None:
            delay = min(60, 2 ** attempt)
        log.warning("Jira %s; retrying in %.0fs (attempt %d/%d)", reason, delay, attempt, self.cfg.max_retries)
        time.sleep(delay)


def _http_error(r: requests.Response) -> JiraError:
    snippet = r.text[:300].replace("\n", " ")
    err = JiraError(f"Jira returned HTTP {r.status_code} for {r.url}: {snippet}")
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
