"""Walking-skeleton end-to-end tests: config -> ingest -> Postgres -> FastAPI -> Jinja2.

These tests assert on rendered HTTP/HTML content, not internal return values --
the point of a skeleton test is that it breaks if any layer of the stack is
disconnected. Every HTTP call here goes through fastapi.testclient.TestClient,
which is an in-process ASGI call, not a live network request -- no outbound
HTTP client call of any kind appears anywhere in this file.
"""

from fastapi.testclient import TestClient

from techtrend.ingest import main as ingest_main


def _seed_one_entity(conn):
    """Insert one entity + an eligible scores row directly (bypasses
    ingest/score) for dashboard tests.

    As of plan 01-06, `query_ranked` joins on `scores.eligible = 1 AND
    scores.score_version = CURRENT_SCORE_VERSION` (the score_version/eligible
    defect fix flagged in 01-04-SUMMARY.md) -- an entity with no `scores` row
    no longer renders on the dashboard at all, so this fixture must seed one
    directly rather than relying on the entities row alone.
    """
    from techtrend.pipeline.score import CURRENT_SCORE_VERSION

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
    entity_id = conn.execute(
        "SELECT id FROM entities WHERE source = 'github' AND source_native_id = '741883704'"
    ).fetchone()["id"]
    conn.execute(
        """
        INSERT INTO scores (
            entity_id, run_date, score_version, stars_gained,
            window_days, wilson_lower_bound, eligible
        ) VALUES (%(entity_id)s, '2026-07-19', %(score_version)s, 100, 7, 0.5, 1)
        """,
        {"entity_id": entity_id, "score_version": CURRENT_SCORE_VERSION},
    )
    conn.commit()


def _row_counts(conn):
    counts = {}
    for table in ("entities", "snapshots", "run_manifest"):
        counts[table] = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    return counts


def _make_client():
    """Depends on the `pg_env` fixture already having pointed
    techtrend.db.connection.connect()'s zero-arg PG* env-var path at the
    ephemeral test database -- callers must also request `pg_env`.
    """
    from techtrend.server.app import app

    return TestClient(app)


def test_fixture_ingest_writes_entity_and_snapshot(db, pg_env):
    exit_code = ingest_main(["--fixture"])
    assert exit_code == 0

    entity_count = db.execute("SELECT COUNT(*) AS n FROM entities").fetchone()["n"]
    snapshot_count = db.execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()["n"]

    assert entity_count >= 1
    assert snapshot_count >= 1


def test_dashboard_renders_seeded_repo(db, pg_env):
    _seed_one_entity(db)
    client = _make_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "<table" in response.text
    assert "Aider-AI/aider" in response.text


def test_dashboard_row_links_to_source(db, pg_env):
    _seed_one_entity(db)
    client = _make_client()

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="https://github.com/Aider-AI/aider"' in response.text


def test_dashboard_empty_state(db, pg_env):
    client = _make_client()
    response = client.get("/")

    assert response.status_code == 200
    assert "No data yet" in response.text
    assert "python -m techtrend.ingest" in response.text


def test_dashboard_never_writes(db, pg_env):
    _seed_one_entity(db)
    client = _make_client()

    before = _row_counts(db)
    response = client.get("/")
    after = _row_counts(db)

    assert response.status_code == 200
    assert before == after
