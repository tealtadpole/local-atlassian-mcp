from __future__ import annotations

from pathlib import Path

import pytest

from fake_jira import EMAIL, TOKEN
from jira_mcp.config import load_config

HERE = Path(__file__).parent


@pytest.fixture
def fake():
    from fake_jira import FakeJira

    f = FakeJira(projects=["ENG", "OPS"])
    yield f
    f.stop()


@pytest.fixture
def make_config(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", TOKEN)

    def make(base_url: str, projects=(), **sections) -> object:
        extra = ""
        for name, values in sections.items():
            extra += f"\n[{name}]\n" + "\n".join(f"{k} = {_toml(v)}" for k, v in values.items())
        cfg = tmp_path / "config.toml"
        cfg.write_text(f"""
[jira]
base_url = "{base_url}"
email = "{EMAIL}"
projects = {_toml(list(projects))}
request_delay_seconds = 0
max_retries = 2
{extra}
""")
        return load_config(cfg)

    return make


def _toml(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    return f'"{v}"'
