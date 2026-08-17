"""Storage layer tests: connection health, schema bootstrap, and the three
uniqueness constraints DATA-05 idempotency relies on.

Covers DATA-01, DATA-02, DATA-03, HEALTH-01.
"""


def test_connect_opens_a_healthy_dict_row_connection(db):
    # WAL mode / busy_timeout were SQLite-specific PRAGMAs with no Postgres
    # equivalent and were dropped in the sqlite->postgres migration; this
    # test instead asserts the connection is live and yields key-accessible
    # (dict_row) rows.
    row = db.execute("SELECT 1 AS one").fetchone()

    assert row["one"] == 1


def test_init_db_is_idempotent(db):
    from techtrend.db.connection import init_db

    # db fixture already called init_db once; call again and confirm no error
    # and exactly five user tables (Phase 2 adds `enrichments`).
    init_db(db)

    tables = sorted(
        row["table_name"]
        for row in db.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
    )
    assert tables == ["enrichments", "entities", "run_manifest", "scores", "snapshots"]


def test_entities_upsert_is_idempotent_on_source_and_native_id(db, frozen_now):
    now = frozen_now.isoformat()

    def upsert(full_name, url):
        db.execute(
            """
            INSERT INTO entities
                (source, source_native_id, full_name, url,
                 discovery_method, admitted_at, last_seen_at)
            VALUES
                ('github', '12345', %s, %s, 'seed', %s, %s)
            ON CONFLICT(source, source_native_id) DO UPDATE SET
                full_name = excluded.full_name,
                url = excluded.url,
                last_seen_at = excluded.last_seen_at
            """,
            (full_name, url, now, now),
        )
        db.commit()

    upsert("owner/repo", "https://github.com/owner/repo")
    upsert("owner/renamed-repo", "https://github.com/owner/renamed-repo")

    rows = db.execute(
        "SELECT full_name, url FROM entities WHERE source = 'github' AND source_native_id = '12345'"
    ).fetchall()

    assert len(rows) == 1
    assert rows[0]["full_name"] == "owner/renamed-repo"
    assert rows[0]["url"] == "https://github.com/owner/renamed-repo"


def test_snapshots_upsert_is_idempotent_on_entity_date_metric(db, frozen_now):
    now = frozen_now.isoformat()
    cur = db.execute(
        """
        INSERT INTO entities
            (source, source_native_id, full_name, url, discovery_method, admitted_at, last_seen_at)
        VALUES
            ('github', '999', 'owner/repo', 'https://github.com/owner/repo', 'seed', %s, %s)
        RETURNING id
        """,
        (now, now),
    )
    entity_id = cur.fetchone()["id"]
    db.commit()

    collected_at = "2026-07-19"

    def upsert_snapshot(value):
        db.execute(
            """
            INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value, source_kind)
            VALUES (%s, %s, 'stars', %s, 'observed')
            ON CONFLICT(entity_id, collected_at, metric_name) DO UPDATE SET
                metric_value = excluded.metric_value
            """,
            (entity_id, collected_at, value),
        )
        db.commit()

    upsert_snapshot(100)
    upsert_snapshot(150)

    rows = db.execute(
        """
        SELECT metric_value FROM snapshots
        WHERE entity_id = %s AND collected_at = %s AND metric_name = 'stars'
        """,
        (entity_id, collected_at),
    ).fetchall()

    assert len(rows) == 1
    assert rows[0]["metric_value"] == 150


def test_run_manifest_write_is_idempotent_on_run_date_and_stage(db):
    def write_manifest(status, started_at):
        db.execute(
            """
            INSERT INTO run_manifest (run_date, stage, status, item_count, started_at)
            VALUES ('2026-07-19', 'collect:github', %s, %s, %s)
            ON CONFLICT(run_date, stage) DO UPDATE SET
                status = excluded.status,
                item_count = excluded.item_count,
                started_at = excluded.started_at
            """,
            (status, 10, started_at),
        )
        db.commit()

    write_manifest("success", "2026-07-19T09:00:00+00:00")
    write_manifest("success", "2026-07-19T09:05:00+00:00")

    rows = db.execute(
        "SELECT * FROM run_manifest WHERE run_date = '2026-07-19' AND stage = 'collect:github'"
    ).fetchall()

    assert len(rows) == 1


def test_scores_accepts_multiple_score_versions_for_same_entity_and_run_date(db, frozen_now):
    now = frozen_now.isoformat()
    cur = db.execute(
        """
        INSERT INTO entities
            (source, source_native_id, full_name, url, discovery_method, admitted_at, last_seen_at)
        VALUES
            ('github', '555', 'owner/repo', 'https://github.com/owner/repo', 'seed', %s, %s)
        RETURNING id
        """,
        (now, now),
    )
    entity_id = cur.fetchone()["id"]
    db.commit()

    db.execute(
        """
        INSERT INTO scores
            (entity_id, run_date, score_version, stars_gained,
             window_days, wilson_lower_bound, eligible)
        VALUES (%s, '2026-07-19', 1, 50, 7, 0.42, 1)
        """,
        (entity_id,),
    )
    db.execute(
        """
        INSERT INTO scores
            (entity_id, run_date, score_version, stars_gained,
             window_days, wilson_lower_bound, eligible)
        VALUES (%s, '2026-07-19', 2, 55, 7, 0.45, 1)
        """,
        (entity_id,),
    )
    db.commit()

    rows = db.execute(
        """
        SELECT score_version FROM scores
        WHERE entity_id = %s AND run_date = '2026-07-19'
        ORDER BY score_version
        """,
        (entity_id,),
    ).fetchall()

    assert [r["score_version"] for r in rows] == [1, 2]
