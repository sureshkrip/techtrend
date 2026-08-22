"""Tests for techtrend.config.load_config()'s enrichment env-var overrides.

Network-free and DB-free: these tests only exercise config loading against
the real, read-only config/tracked.toml. No fixture file is written or
mutated.
"""

from techtrend.config import load_config

ENV_VARS = (
    "TECHTREND_ENRICHMENT_PROVIDER",
    "TECHTREND_ENRICHMENT_BASE_URL",
    "TECHTREND_ENRICHMENT_MODEL",
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


def test_empty_string_env_treated_as_unset(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_MODEL", "")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_PROVIDER", "")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_BASE_URL", "")
    config = load_config()
    assert config.tunables.enrichment_model == "glm-4.7-flash"
    assert config.tunables.enrichment_provider == "openai"
    assert config.tunables.enrichment_base_url == "https://api.z.ai/api/paas/v4/"


def test_overrides_do_not_affect_other_tunables(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TECHTREND_ENRICHMENT_MODEL", "test-model")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_PROVIDER", "test-provider")
    monkeypatch.setenv("TECHTREND_ENRICHMENT_BASE_URL", "https://example.test/v1")
    config = load_config()
    assert config.tunables.enrichment_cap == 15
    assert config.tunables.window_days == 7
