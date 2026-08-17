"""Env-overridable path resolution (deploy prerequisite).

A container mounts a persistent volume and sets TECHTREND_DATA_DIR so the DB,
cache, and logs survive redeploys; local dev with no env vars keeps the original
repo-relative layout. `config/tracked.toml` is image-baked and must NOT relocate
under TECHTREND_DATA_DIR.
"""

import importlib
from pathlib import Path

from techtrend import paths


def test_resolve_places_path_under_data_dir(monkeypatch):
    monkeypatch.setattr(paths, "_DATA_DIR", "/data")
    monkeypatch.delenv("TECHTREND_DB", raising=False)
    assert paths._resolve("TECHTREND_DB", "techtrend.db", "techtrend.db") == (
        Path("/data") / "techtrend.db"
    )


def test_resolve_explicit_override_beats_data_dir(monkeypatch):
    monkeypatch.setattr(paths, "_DATA_DIR", "/data")
    monkeypatch.setenv("TECHTREND_DB", "/custom/mydb.sqlite")
    assert paths._resolve("TECHTREND_DB", "techtrend.db", "techtrend.db") == Path(
        "/custom/mydb.sqlite"
    )


def test_resolve_bare_default_when_nothing_set(monkeypatch):
    monkeypatch.setattr(paths, "_DATA_DIR", None)
    monkeypatch.delenv("TECHTREND_DB", raising=False)
    assert paths._resolve("TECHTREND_DB", "techtrend.db", "techtrend.db") == Path(
        "techtrend.db"
    )


def test_data_dir_relocates_runtime_state_but_not_config(monkeypatch):
    """With TECHTREND_DATA_DIR set, the module-level constants that back the
    cache/log defaults live under it; CONFIG_PATH does not. Storage itself is
    server-side PostgreSQL (see techtrend/db/connection.py) and has no
    filesystem path to relocate.
    """
    monkeypatch.setenv("TECHTREND_DATA_DIR", "/data")
    for var in ("TECHTREND_CACHE_DIR", "TECHTREND_LOG_FILE", "TECHTREND_CONFIG"):
        monkeypatch.delenv(var, raising=False)
    try:
        importlib.reload(paths)
        assert paths.CACHE_DIR == Path("/data") / ".hishel"
        assert paths.CACHE_DB == Path("/data") / ".hishel" / "github.db"
        assert paths.LOG_FILE == Path("/data") / "logs" / "techtrend.log"
        # config is image-baked — never relocated by TECHTREND_DATA_DIR.
        assert paths.CONFIG_PATH == Path("config/tracked.toml")
    finally:
        # Restore clean module state so later tests see the default layout.
        monkeypatch.delenv("TECHTREND_DATA_DIR", raising=False)
        importlib.reload(paths)
