"""Shared pytest fixtures for the TechTrend test suite.

No test in this phase makes a live network call (the stated testing
philosophy in .claude/CLAUDE.md) -- GitHub responses are recorded fixtures
under tests/fixtures/github/.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from techtrend.db.connection import connect, init_db

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "github"

FROZEN_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    """An initialized WAL-mode SQLite connection against a real temp file.

    A real file (not :memory:) so WAL mode is actually exercised. Closed on
    teardown.
    """
    db_path = tmp_path / "techtrend-test.db"
    conn = connect(db_path)
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def frozen_now():
    """A fixed, timezone-aware datetime so window arithmetic is deterministic."""
    return FROZEN_NOW


@pytest.fixture
def github_fixture():
    """Factory fixture: given a filename in tests/fixtures/github/, returns
    parsed JSON for .json files or raw text for everything else (e.g. readme.md).
    """

    def _load(filename: str):
        path = FIXTURES_DIR / filename
        if path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        return path.read_text(encoding="utf-8")

    return _load
