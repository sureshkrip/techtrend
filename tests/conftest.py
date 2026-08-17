"""Shared pytest fixtures for the TechTrend test suite.

No test in this phase makes a live network call (the stated testing
philosophy in .claude/CLAUDE.md) -- GitHub responses are recorded fixtures
under tests/fixtures/github/.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from psycopg.conninfo import make_conninfo
from pytest_postgresql import factories

from techtrend.db.connection import connect, init_db

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "github"

FROZEN_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)

# Ephemeral Postgres cluster (no Docker) provisioned from locally-installed
# initdb/pg_ctl found on PATH -- postgresql_proc spins up the throwaway
# cluster once per session/worker; postgresql_client provisions a fresh
# database per test on top of it (dropped/recreated via pytest-postgresql's
# DatabaseJanitor).
postgresql_proc = factories.postgresql_proc()
postgresql_client = factories.postgresql("postgresql_proc")


@pytest.fixture
def db(postgresql_client):
    """An initialized psycopg connection against an ephemeral per-test
    Postgres database.

    Connection parameters are derived from the pytest-postgresql client
    fixture's own connection info and passed through `connect()`'s
    `conninfo` injection seam -- never the PG* env vars -- so tests never
    need PGPASSWORD set. Closed on teardown; the underlying database is
    dropped by pytest-postgresql's janitor.
    """
    info = postgresql_client.info
    conninfo = make_conninfo(
        host=info.host,
        port=info.port,
        dbname=info.dbname,
        user=info.user,
        password=info.password,
    )
    conn = connect(conninfo=conninfo)
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
