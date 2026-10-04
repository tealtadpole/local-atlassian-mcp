from __future__ import annotations

from pathlib import Path

import pytest

from atlassian_mcp.config import load_config
from fake_atlassian import EMAIL, TOKEN

HERE = Path(__file__).parent


@pytest.fixture
def fake():
    from fake_atlassian import FakeAtlassian

    f = FakeAtlassian(projects=["ENG", "OPS"], spaces={"ENG": "Engineering", "HR": "People"})
    yield f
    f.stop()


@pytest.fixture
def make_config(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", TOKEN)

    def make(base_url: str, projects=(), spaces=(), **sections) -> object:
        extra = ""
        for name, values in sections.items():
            extra += f"\n[{name}]\n" + "\n".join(f"{k} = {_toml(v)}" for k, v in values.items())
        cfg = tmp_path / "config.toml"
        cfg.write_text(f"""
[atlassian]
base_url = "{base_url}"
email = "{EMAIL}"
request_delay_seconds = 0
max_retries = 2

[jira]
projects = {_toml(list(projects))}

[confluence]
spaces = {_toml(list(spaces))}
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
