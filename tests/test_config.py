"""Tests for techtrend.config.load_config()'s enrichment env-var overrides,
and the curated D3-4 source-list config sections (hn/packages/changelogs).

Network-free and DB-free: these tests only exercise config loading against
the real, read-only config/tracked.toml plus small in-tmp TOML fixtures.
No production fixture file is written or mutated.
"""

from techtrend.config import Config, load_config

ENV_VARS = (
    "TECHTREND_ENRICHMENT_PROVIDER",
    "TECHTREND_ENRICHMENT_BASE_URL",
    "TECHTREND_ENRICHMENT_MODEL",
    "TECHTREND_ENRICHMENT_MAX_TOKENS",
    "TECHTREND_ENRICHMENT_DISABLE_THINKING",
)


def _clear_env(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_enrichment_model_env_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_MODEL", "test-model")
    config = load_config()
    assert config.tunables.enrichment_model == "test-model"


def test_enrichment_provider_env_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_PROVIDER", "test-provider")
    config = load_config()
    assert config.tunables.enrichment_provider == "test-provider"


def test_enrichment_base_url_env_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_BASE_URL", "https://example.test/v1")
    config = load_config()
    assert config.tunables.enrichment_base_url == "https://example.test/v1"


def test_all_unset_falls_back_to_tracked_toml(monkeypatch):
    _clear_env(monkeypatch)
    config = load_config()
    assert config.tunables.enrichment_model == "glm-4.7-flash"
    assert config.tunables.enrichment_provider == "openai"
    assert config.tunables.enrichment_base_url == "https://api.z.ai/api/paas/v4/"
    assert config.tunables.enrichment_max_tokens == 1024
    assert config.tunables.enrichment_disable_thinking is True


def test_enrichment_max_tokens_env_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_MAX_TOKENS", "2048")
    config = load_config()
    assert config.tunables.enrichment_max_tokens == 2048
    assert isinstance(config.tunables.enrichment_max_tokens, int)


def test_enrichment_disable_thinking_env_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_DISABLE_THINKING", "true")
    config = load_config()
    assert config.tunables.enrichment_disable_thinking is True
    assert isinstance(config.tunables.enrichment_disable_thinking, bool)


def test_empty_string_env_treated_as_unset(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_MODEL", "")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_PROVIDER", "")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_BASE_URL", "")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_MAX_TOKENS", "")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_DISABLE_THINKING", "")
    config = load_config()
    assert config.tunables.enrichment_model == "glm-4.7-flash"
    assert config.tunables.enrichment_provider == "openai"
    assert config.tunables.enrichment_base_url == "https://api.z.ai/api/paas/v4/"
    assert config.tunables.enrichment_max_tokens == 1024
    assert config.tunables.enrichment_disable_thinking is True


def test_overrides_do_not_affect_other_tunables(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_MODEL", "test-model")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_PROVIDER", "test-provider")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_BASE_URL", "https://example.test/v1")
    config = load_config()
    assert config.tunables.enrichment_cap == 15
    assert config.tunables.window_days == 7


# ---------------------------------------------------------------------------
# D3-4 curated source-list config sections (hn/packages/changelogs)
# ---------------------------------------------------------------------------


def test_real_tracked_toml_exposes_hn_packages_changelogs():
    config = load_config()
    assert config.hn.keywords
    assert config.hn.lookback_days == 7
    assert config.packages.npm
    assert config.packages.pypi
    assert config.changelogs
    for feed in config.changelogs:
        assert feed.label
        assert feed.url.startswith("https://")
    # No known-404 vendor blog feed seeded (RESEARCH.md confirmed 404s).
    assert not any(
        "anthropic.com/rss" in feed.url or "ollama.com/blog/rss" in feed.url
        for feed in config.changelogs
    )


def test_partial_toml_with_only_hn_section_still_validates(tmp_path):
    partial = tmp_path / "partial.toml"
    partial.write_text(
        '[hn]\nkeywords = ["llm", "agentic"]\n',
        encoding="utf-8",
    )
    config = load_config(partial)
    assert isinstance(config, Config)
    assert config.hn.keywords == ["llm", "agentic"]
    assert config.hn.lookback_days == 7
    # Every other section falls back to its empty/default value.
    assert config.packages.npm == []
    assert config.packages.pypi == []
    assert config.changelogs == []
    assert config.seed.repos == []
    assert config.tunables.window_days == 7
