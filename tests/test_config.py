import pytest

from atlassian_mcp.config import ConfigError, load_config

BASE = """
[atlassian]
base_url = "https://corp.atlassian.net"
email = "tester@example.com"
"""


def write(tmp_path, text, mode=0o600):
    p = tmp_path / "config.toml"
    p.write_text(text)
    p.chmod(mode)
    return p


def test_env_token_wins_over_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "from-env")
    cfg = load_config(write(tmp_path, BASE + 'token = "from-file"\n'))
    assert cfg.atlassian.token == "from-env"
    assert "from-env" not in repr(cfg.atlassian)


def test_file_token_and_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLASSIAN_API_TOKEN", raising=False)
    cfg = load_config(write(tmp_path, BASE + 'token = "from-file"\n'))
    assert cfg.atlassian.token == "from-file"
    assert cfg.jira.enabled and cfg.confluence.enabled
    assert cfg.jira.projects == () and cfg.confluence.spaces == ()
    assert cfg.search.default_results == 10


def test_missing_token(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLASSIAN_API_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="No Atlassian API token"):
        load_config(write(tmp_path, BASE))


def test_missing_email(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "t")
    with pytest.raises(ConfigError, match="atlassian.email"):
        load_config(write(tmp_path, '[atlassian]\nbase_url = "https://corp.atlassian.net"\n'))


def test_example_value_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "t")
    text = '[atlassian]\nbase_url = "https://example.atlassian.net"\nemail = "t@example.com"\n'
    with pytest.raises(ConfigError, match="still the example value"):
        load_config(write(tmp_path, text))


def test_typo_in_key_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "t")
    with pytest.raises(ConfigError, match="projecs"):
        load_config(write(tmp_path, BASE + '\n[jira]\nprojecs = ["ENG"]\n'))


def test_projects_and_spaces_allow_lists(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "t")
    text = BASE + '\n[jira]\nprojects = ["ENG", "OPS"]\n\n[confluence]\nspaces = ["ENG", "HR"]\n'
    cfg = load_config(write(tmp_path, text))
    assert cfg.jira.projects == ("ENG", "OPS")
    assert cfg.confluence.spaces == ("ENG", "HR")


def test_both_products_disabled_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "t")
    text = BASE + "\n[jira]\nenabled = false\n\n[confluence]\nenabled = false\n"
    with pytest.raises(ConfigError, match="Enable at least one"):
        load_config(write(tmp_path, text))


def test_default_exceeds_max_results_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "t")
    text = BASE + "\n[search]\ndefault_results = 100\nmax_results = 50\n"
    with pytest.raises(ConfigError, match="default_results"):
        load_config(write(tmp_path, text))
