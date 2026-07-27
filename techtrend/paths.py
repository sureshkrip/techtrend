"""Env-overridable filesystem paths for all mutable state.

Local dev keeps the original layout (repo-relative `techtrend.db`, `.hishel/`,
`logs/`). A containerized deploy points these at a persistent volume instead of
the ephemeral container filesystem — without which every redeploy silently
wipes the accumulated snapshot history that is the whole point of the tool.

The simplest deploy knob is `TECHTREND_DATA_DIR` (e.g. `/data`, a mounted
volume): the DB, HTTP cache, and log file all relocate under it. Each path also
has an individual override for finer control. `config/tracked.toml` deliberately
does NOT follow `TECHTREND_DATA_DIR` — it is baked into the image as read-only
config, not runtime state; override it explicitly with `TECHTREND_CONFIG` only
if you mount an editable config.

Constants are resolved once at import. Real environment variables (Coolify,
Task Scheduler) are set before the process starts; a local `.env` is loaded
here so `TECHTREND_*` overrides work in development too.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_DATA_DIR = os.environ.get("TECHTREND_DATA_DIR")


def _resolve(env_key: str, subpath: str, bare_default: str) -> Path:
    """Explicit per-path env override wins; else place `subpath` under
    TECHTREND_DATA_DIR when that is set; else the original repo-relative default.
    """
    explicit = os.environ.get(env_key)
    if explicit:
        return Path(explicit)
    if _DATA_DIR:
        return Path(_DATA_DIR) / subpath
    return Path(bare_default)


DB_PATH = _resolve("TECHTREND_DB", "techtrend.db", "techtrend.db")
CACHE_DIR = _resolve("TECHTREND_CACHE_DIR", ".hishel", ".hishel")
CACHE_DB = CACHE_DIR / "github.db"
LOG_FILE = _resolve("TECHTREND_LOG_FILE", "logs/techtrend.log", "logs/techtrend.log")
# config is image-baked read-only config, NOT runtime state — never follows DATA_DIR.
CONFIG_PATH = Path(os.environ.get("TECHTREND_CONFIG") or "config/tracked.toml")
