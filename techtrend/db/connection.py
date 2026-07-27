"""WAL-mode SQLite connection helper and schema bootstrap.

RESEARCH.md's concurrency note: one connection per caller, never a shared
cross-thread connection -- check_same_thread is left at its default True.
"""

import sqlite3
from pathlib import Path

from techtrend import paths

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Env-overridable (TECHTREND_DB / TECHTREND_DATA_DIR) so a container can write to
# a persistent volume; defaults to repo-relative techtrend.db for local dev.
DEFAULT_DB_PATH = paths.DB_PATH


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL journaling and a busy timeout.

    Sets row_factory to sqlite3.Row and enables foreign key enforcement.
    Does NOT bootstrap the schema -- call init_db(conn) separately.
    """
    resolved = db_path if db_path is not None else DEFAULT_DB_PATH
    resolved.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Bootstrap the four-table schema. Idempotent -- safe to call more than once."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
