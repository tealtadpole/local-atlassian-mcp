"""Load and validate config.toml."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ENV_CONFIG_PATH = "JIRA_MCP_CONFIG"
DEFAULT_LOCATIONS = (
    Path("config.toml"),
    Path("~/.config/jira-mcp/config.toml").expanduser(),
)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    email: str
    token: str
    projects: tuple[str, ...] = ()
    verify_ssl: bool | str = True
    timeout_seconds: float = 30
    request_delay_seconds: float = 0
    max_retries: int = 5

    def __repr__(self) -> str:  # keep the token out of logs and tracebacks
        return (f"JiraConfig(base_url={self.base_url!r}, email={self.email!r}, "
                f"projects={self.projects!r})")


@dataclass(frozen=True)
class SearchConfig:
    default_results: int = 10
    max_results: int = 50


@dataclass(frozen=True)
class Config:
    path: Path
    jira: JiraConfig
    search: SearchConfig


def find_config(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"Config file not found: {path}")
        return path.resolve()
    if env := os.environ.get(ENV_CONFIG_PATH):
        return find_config(env)
    for candidate in DEFAULT_LOCATIONS:
        if candidate.is_file():
            return candidate.resolve()
    searched = ", ".join(str(p) for p in DEFAULT_LOCATIONS)
    raise ConfigError(
        f"No config file found (searched {searched}). Copy config.example.toml to "
        f"config.toml, or pass --config / set ${ENV_CONFIG_PATH}."
    )


def load_config(explicit: str | os.PathLike | None = None) -> Config:
    path = find_config(explicit)
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e

    unknown = set(raw) - {"jira", "search"}
    if unknown:
        raise ConfigError(f"{path}: unknown section(s): {', '.join(sorted(unknown))}")

    jira = _jira_section(raw.get("jira", {}), path)
    search = _section(SearchConfig, raw.get("search", {}), "search")
    if search.default_results > search.max_results:
        raise ConfigError("search.default_results must not exceed search.max_results")

    return Config(path=path, jira=jira, search=search)


def _jira_section(raw: dict[str, Any], path: Path) -> JiraConfig:
    raw = dict(raw)
    token_env = raw.pop("token_env", "JIRA_API_TOKEN")
    file_token = raw.pop("token", "")
    token = os.environ.get(token_env, "") if token_env else ""
    if not token and file_token:
        token = file_token
        if path.stat().st_mode & 0o077:
            log.warning("%s contains a token but is readable by other users; run: chmod 600 %s",
                        path, path)
    if not token:
        raise ConfigError(f"No Jira API token: set ${token_env} or jira.token in {path}")

    email = str(raw.get("email", ""))
    if "@" not in email:
        raise ConfigError("jira.email must be the Atlassian account email for the API token")

    base_url = str(raw.get("base_url", "")).rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise ConfigError("jira.base_url must be an http(s) URL")
    if base_url.startswith("http://"):
        log.warning("jira.base_url uses plain http; your credentials are sent unencrypted")
    if "example.atlassian.net" in base_url:
        raise ConfigError("jira.base_url is still the example value; set your Jira site URL")

    projects = raw.get("projects", [])
    if not isinstance(projects, list) or not all(isinstance(p, str) for p in projects):
        raise ConfigError("jira.projects must be a list of project keys")
    raw["projects"] = tuple(projects)

    verify = raw.get("verify_ssl", True)
    if isinstance(verify, str):
        verify_path = _resolve(verify, path.parent)
        if not verify_path.exists():
            raise ConfigError(f"jira.verify_ssl CA bundle not found: {verify_path}")
        raw["verify_ssl"] = str(verify_path)

    raw["base_url"] = base_url
    return _section(JiraConfig, raw, "jira", extra={"token": token})


def _section(cls, raw: dict[str, Any], name: str, *, defaults=None, extra=None):
    allowed = {f.name for f in fields(cls)} - set(extra or {})
    unknown = set(raw) - allowed
    if unknown:
        raise ConfigError(f"unknown key(s) in [{name}]: {', '.join(sorted(unknown))}")
    values = {**(defaults or {}), **raw, **(extra or {})}
    try:
        return cls(**values)
    except TypeError as e:
        raise ConfigError(f"[{name}]: {e}") from e


def _resolve(value: str | Path, base: Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()
