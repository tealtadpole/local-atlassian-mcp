import pytest

from jira_mcp.config import ConfigError, load_config

BASE = """
[jira]
base_url = "https://corp.atlassian.net"
email = "tester@example.com"
"""


def write(tmp_path, text, mode=0o600):
    p = tmp_path / "config.toml"
    p.write_text(text)
    p.chmod(mode)
    return p


def test_env_token_wins_over_file(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "from-env")
    cfg = load_config(write(tmp_path, BASE + 'token = "from-file"\n'))
    assert cfg.jira.token == "from-env"
    assert "from-env" not in repr(cfg.jira)


def test_file_token_and_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    cfg = load_config(write(tmp_path, BASE + 'token = "from-file"\n'))
    assert cfg.jira.token == "from-file"
    assert cfg.jira.projects == ()
    assert cfg.search.default_results == 10


def test_missing_token(tmp_path, monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="No Jira API token"):
        load_config(write(tmp_path, BASE))


def test_missing_email(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    with pytest.raises(ConfigError, match="jira.email"):
        load_config(write(tmp_path, '[jira]\nbase_url = "https://corp.atlassian.net"\n'))


def test_example_value_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    text = '[jira]\nbase_url = "https://example.atlassian.net"\nemail = "t@example.com"\n'
    with pytest.raises(ConfigError, match="still the example value"):
        load_config(write(tmp_path, text))


def test_typo_in_key_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    with pytest.raises(ConfigError, match="projecs"):
        load_config(write(tmp_path, BASE + 'projecs = ["ENG"]\n'))


def test_projects_allow_list(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    cfg = load_config(write(tmp_path, BASE + 'projects = ["ENG", "OPS"]\n'))
    assert cfg.jira.projects == ("ENG", "OPS")


def test_default_exceeds_max_results_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    text = BASE + "\n[search]\ndefault_results = 100\nmax_results = 50\n"
    with pytest.raises(ConfigError, match="default_results"):
        load_config(write(tmp_path, text))
