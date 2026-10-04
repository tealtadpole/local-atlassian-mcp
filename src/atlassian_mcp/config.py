"""Load and validate config.toml."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ENV_CONFIG_PATH = "ATLASSIAN_MCP_CONFIG"
DEFAULT_LOCATIONS = (
    Path("config.toml"),
    Path("~/.config/atlassian-mcp/config.toml").expanduser(),
)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class AtlassianConfig:
    """Connection shared by Jira Cloud and Confluence Cloud: same site, same auth."""

    base_url: str
    email: str
    token: str
    verify_ssl: bool | str = True
    timeout_seconds: float = 30
    request_delay_seconds: float = 0
    max_retries: int = 5

    def __repr__(self) -> str:  # keep the token out of logs and tracebacks
        return f"AtlassianConfig(base_url={self.base_url!r}, email={self.email!r})"


@dataclass(frozen=True)
class JiraConfig:
    enabled: bool = True
    projects: tuple[str, ...] = ()   # optional allow-list; empty = whatever the token can see


@dataclass(frozen=True)
class ConfluenceConfig:
    enabled: bool = True
    spaces: tuple[str, ...] = ()   # optional allow-list; empty = whatever the token can see


@dataclass(frozen=True)
class SearchConfig:
    default_results: int = 10
    max_results: int = 50


@dataclass(frozen=True)
class Config:
    path: Path
    atlassian: AtlassianConfig
    jira: JiraConfig
    confluence: ConfluenceConfig
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

    unknown = set(raw) - {"atlassian", "jira", "confluence", "search"}
    if unknown:
        raise ConfigError(f"{path}: unknown section(s): {', '.join(sorted(unknown))}")

    atlassian = _atlassian_section(raw.get("atlassian", {}), path)
    jira = _section(JiraConfig, _tuples(raw.get("jira", {}), "projects"), "jira")
    confluence = _section(ConfluenceConfig, _tuples(raw.get("confluence", {}), "spaces"), "confluence")
    search = _section(SearchConfig, raw.get("search", {}), "search")

    if not (jira.enabled or confluence.enabled):
        raise ConfigError("Enable at least one of [jira] or [confluence]")
    if search.default_results > search.max_results:
        raise ConfigError("search.default_results must not exceed search.max_results")

    return Config(path=path, atlassian=atlassian, jira=jira, confluence=confluence, search=search)


def _atlassian_section(raw: dict[str, Any], path: Path) -> AtlassianConfig:
    raw = dict(raw)
    token_env = raw.pop("token_env", "ATLASSIAN_API_TOKEN")
    file_token = raw.pop("token", "")
    token = os.environ.get(token_env, "") if token_env else ""
    if not token and file_token:
        token = file_token
        if path.stat().st_mode & 0o077:
            log.warning("%s contains a token but is readable by other users; run: chmod 600 %s",
                        path, path)
    if not token:
        raise ConfigError(f"No Atlassian API token: set ${token_env} or atlassian.token in {path}")

    email = str(raw.get("email", ""))
    if "@" not in email:
        raise ConfigError("atlassian.email must be the Atlassian account email for the API token")

    base_url = str(raw.get("base_url", "")).rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise ConfigError("atlassian.base_url must be an http(s) URL")
    if base_url.startswith("http://"):
        log.warning("atlassian.base_url uses plain http; your credentials are sent unencrypted")
    if "example.atlassian.net" in base_url:
        raise ConfigError("atlassian.base_url is still the example value; set your Atlassian site URL")

    verify = raw.get("verify_ssl", True)
    if isinstance(verify, str):
        verify_path = _resolve(verify, path.parent)
        if not verify_path.exists():
            raise ConfigError(f"atlassian.verify_ssl CA bundle not found: {verify_path}")
        raw["verify_ssl"] = str(verify_path)

    raw["base_url"] = base_url
    return _section(AtlassianConfig, raw, "atlassian", extra={"token": token})


def _tuples(values: dict[str, Any], *keys: str) -> dict[str, Any]:
    out = dict(values)
    for k in keys:
        if k in out:
            if not isinstance(out[k], list):
                raise ConfigError(f"`{k}` must be a list")
            out[k] = tuple(out[k])
    return out


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
