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
# A second, independent ephemeral database on the same throwaway cluster --
# for tests that need to prove behavior is identical across two distinct DB
# instances (e.g. order-independence tests), where a single shared `db`
# connection can't demonstrate the same-tables-different-instances claim.
postgresql_second_client = factories.postgresql("postgresql_proc", dbname="tests_second")


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
def second_db(postgresql_second_client):
    """A second, independent ephemeral Postgres database (same cluster,
    separate database) -- for tests that need two distinct DB instances,
    e.g. proving that resolving the same item set in a different order
    produces an identical table in a wholly separate database.
    """
    info = postgresql_second_client.info
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
def pg_env(postgresql_client, monkeypatch):
    """Points the five PG* env vars that `connect()`'s zero-arg path reads
    (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD -- exactly what production
    code calls) at the same ephemeral per-test Postgres database the `db`
    fixture uses.

    Needed by tests that exercise a real `connect()`-with-no-args code path
    they don't control directly -- e.g. the FastAPI TestClient route handler
    (techtrend.server.app.dashboard calls `connect()`) or `ingest.main()` --
    where there is no positional-arg seam left to inject a test connection.
    """
    info = postgresql_client.info
    monkeypatch.setenv("PGHOST", info.host)
    monkeypatch.setenv("PGPORT", str(info.port))
    monkeypatch.setenv("PGDATABASE", info.dbname)
    monkeypatch.setenv("PGUSER", info.user)
    if info.password:
        monkeypatch.setenv("PGPASSWORD", info.password)
    else:
        monkeypatch.delenv("PGPASSWORD", raising=False)


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
