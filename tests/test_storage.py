"""Storage layer tests: WAL connection, schema bootstrap, and the three
uniqueness constraints DATA-05 idempotency relies on.

Covers DATA-01, DATA-02, DATA-03, HEALTH-01.
"""


def test_connect_enables_wal_and_busy_timeout(db):
    journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    busy_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode == "wal"
    assert busy_timeout == 5000


def test_init_db_is_idempotent(db):
    from techtrend.db.connection import init_db

    # db fixture already called init_db once; call again and confirm no error
    # and exactly five user tables (Phase 2 adds `enrichments`).
    init_db(db)

    tables = sorted(
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
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
                ('github', '12345', ?, ?, 'seed', ?, ?)
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
            ('github', '999', 'owner/repo', 'https://github.com/owner/repo', 'seed', ?, ?)
        """,
        (now, now),
    )
    entity_id = cur.lastrowid
    db.commit()

    collected_at = "2026-07-19"

    def upsert_snapshot(value):
        db.execute(
            """
            INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value, source_kind)
            VALUES (?, ?, 'stars', ?, 'observed')
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
        WHERE entity_id = ? AND collected_at = ? AND metric_name = 'stars'
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
            VALUES ('2026-07-19', 'collect:github', ?, ?, ?)
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
            ('github', '555', 'owner/repo', 'https://github.com/owner/repo', 'seed', ?, ?)
        """,
        (now, now),
    )
    entity_id = cur.lastrowid
    db.commit()

    db.execute(
        """
        INSERT INTO scores
            (entity_id, run_date, score_version, stars_gained,
             window_days, wilson_lower_bound, eligible)
        VALUES (?, '2026-07-19', 1, 50, 7, 0.42, 1)
        """,
        (entity_id,),
    )
    db.execute(
        """
        INSERT INTO scores
            (entity_id, run_date, score_version, stars_gained,
             window_days, wilson_lower_bound, eligible)
        VALUES (?, '2026-07-19', 2, 55, 7, 0.45, 1)
        """,
        (entity_id,),
    )
    db.commit()

    rows = db.execute(
        """
        SELECT score_version FROM scores
        WHERE entity_id = ? AND run_date = '2026-07-19'
        ORDER BY score_version
        """,
        (entity_id,),
    ).fetchall()

    assert [r["score_version"] for r in rows] == [1, 2]
