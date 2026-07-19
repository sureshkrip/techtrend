"""Walking-skeleton end-to-end tests: config -> ingest -> SQLite -> FastAPI -> Jinja2.

These tests assert on rendered HTTP/HTML content, not internal return values --
the point of a skeleton test is that it breaks if any layer of the stack is
disconnected. Every HTTP call here goes through fastapi.testclient.TestClient,
which is an in-process ASGI call, not a live network request -- no outbound
HTTP client call of any kind appears anywhere in this file.
"""

import sqlite3

from fastapi.testclient import TestClient

from techtrend.db.connection import connect, init_db
from techtrend.ingest import main as ingest_main


def _seed_one_entity(db_path):
    """Insert one entity + snapshot directly (bypasses ingest) for dashboard tests."""
    conn = connect(db_path)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, homepage,
            discovery_method, admitted_at, last_seen_at
        ) VALUES (
            'github', '741883704', 'Aider-AI/aider', 'https://github.com/Aider-AI/aider',
            'https://aider.chat', 'seed', '2026-07-19T00:00:00Z', '2026-07-19T00:00:00Z'
        )
        """
    )
    conn.commit()
    conn.close()


def _row_counts(db_path):
    conn = sqlite3.connect(db_path)
    counts = {}
    for table in ("entities", "snapshots", "run_manifest"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return counts


def _make_client(monkeypatch, db_path):
    """Point techtrend.server.app's DB dependency at a temp DB path via monkeypatch."""
    import techtrend.db.connection as connection_module

    monkeypatch.setattr(connection_module, "DEFAULT_DB_PATH", db_path)
    from techtrend.server.app import app

    return TestClient(app)


def test_fixture_ingest_writes_entity_and_snapshot(tmp_path, monkeypatch):
    import techtrend.db.connection as connection_module

    db_path = tmp_path / "skeleton-ingest.db"
    monkeypatch.setattr(connection_module, "DEFAULT_DB_PATH", db_path)

    exit_code = ingest_main(["--fixture"])
    assert exit_code == 0

    conn = sqlite3.connect(db_path)
    entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    snapshot_count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    conn.close()

    assert entity_count >= 1
    assert snapshot_count >= 1


def test_dashboard_renders_seeded_repo(tmp_path, monkeypatch):
    db_path = tmp_path / "skeleton-dashboard.db"
    _seed_one_entity(db_path)
    client = _make_client(monkeypatch, db_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "<table" in response.text
    assert "Aider-AI/aider" in response.text


def test_dashboard_row_links_to_source(tmp_path, monkeypatch):
    db_path = tmp_path / "skeleton-links.db"
    _seed_one_entity(db_path)
    client = _make_client(monkeypatch, db_path)

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="https://github.com/Aider-AI/aider"' in response.text


def test_dashboard_empty_state(tmp_path, monkeypatch):
    import techtrend.db.connection as connection_module

    db_path = tmp_path / "skeleton-empty.db"
    monkeypatch.setattr(connection_module, "DEFAULT_DB_PATH", db_path)
    conn = connect(db_path)
    init_db(conn)
    conn.close()

    client = _make_client(monkeypatch, db_path)
    response = client.get("/")

    assert response.status_code == 200
    assert "No data yet" in response.text
    assert "python -m techtrend.ingest" in response.text


def test_dashboard_never_writes(tmp_path, monkeypatch):
    db_path = tmp_path / "skeleton-readonly.db"
    _seed_one_entity(db_path)
    client = _make_client(monkeypatch, db_path)

    before = _row_counts(db_path)
    response = client.get("/")
    after = _row_counts(db_path)

    assert response.status_code == 200
    assert before == after
