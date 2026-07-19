"""Jaccard rank-overlap stability metric tests (SCORE-05, D-12).

D-12: ship the 7-day-window-plus-Wilson-bound scorer with NO additional
damping in Phase 1, and log a stability metric each run so the need for
further smoothing is discovered empirically rather than assumed. EWMA
smoothing and rank hysteresis are both explicitly rejected -- hysteresis
specifically because it would make the displayed rank depend on yesterday's
rank, breaking the "scores are a pure function of (entities, snapshots)"
property.
"""

from datetime import date

import pytest


def test_rank_overlap_empty_sets():
    """Both sets empty -> 1.0, never a ZeroDivisionError on an empty union."""
    from techtrend.pipeline.stability import rank_overlap

    assert rank_overlap(set(), set()) == 1.0


def test_rank_overlap_partial():
    from techtrend.pipeline.stability import rank_overlap

    assert rank_overlap({1, 2, 3}, {2, 3, 4}) == 0.5


def test_rank_overlap_identical_sets():
    from techtrend.pipeline.stability import rank_overlap

    assert rank_overlap({1, 2, 3}, {1, 2, 3}) == 1.0


def test_rank_overlap_one_empty_one_not():
    from techtrend.pipeline.stability import rank_overlap

    assert rank_overlap({1, 2}, set()) == 0.0


def _insert_entity(conn, native_id):
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, discovery_method,
            admitted_at, last_seen_at
        ) VALUES (
            'github', :native_id, :full_name, :url, 'seed',
            '2026-07-01T00:00:00Z', '2026-07-19T00:00:00Z'
        )
        """,
        {
            "native_id": native_id,
            "full_name": f"owner/{native_id}",
            "url": f"https://github.com/owner/{native_id}",
        },
    )
    return conn.execute(
        "SELECT id FROM entities WHERE source_native_id = ?", (native_id,)
    ).fetchone()["id"]


def _insert_score(conn, entity_id, run_date_str, bound, score_version, eligible=1):
    conn.execute(
        """
        INSERT INTO scores (
            entity_id, run_date, score_version, stars_gained,
            window_days, wilson_lower_bound, eligible
        ) VALUES (?, ?, ?, 0, 7, ?, ?)
        """,
        (entity_id, run_date_str, score_version, bound, eligible),
    )


def test_log_stability_warns_below_threshold(db, caplog):
    """A day-to-day top-N whose overlap falls below 0.5 logs at WARNING."""
    import logging

    from techtrend.pipeline.score import CURRENT_SCORE_VERSION
    from techtrend.pipeline.stability import log_stability

    ids = {name: _insert_entity(db, name) for name in ("e1", "e2", "e3", "e4", "e5")}

    # Prior run's top-3: e1, e2, e3.
    _insert_score(db, ids["e1"], "2026-07-18", 0.9, CURRENT_SCORE_VERSION)
    _insert_score(db, ids["e2"], "2026-07-18", 0.8, CURRENT_SCORE_VERSION)
    _insert_score(db, ids["e3"], "2026-07-18", 0.7, CURRENT_SCORE_VERSION)
    # Today's top-3: e3, e4, e5 -- only e3 overlaps -> Jaccard 1/5 = 0.2.
    _insert_score(db, ids["e3"], "2026-07-19", 0.9, CURRENT_SCORE_VERSION)
    _insert_score(db, ids["e4"], "2026-07-19", 0.8, CURRENT_SCORE_VERSION)
    _insert_score(db, ids["e5"], "2026-07-19", 0.7, CURRENT_SCORE_VERSION)
    db.commit()

    with caplog.at_level(logging.WARNING, logger="techtrend.pipeline.stability"):
        overlap = log_stability(db, date(2026, 7, 19), top_n=3)

    assert overlap == pytest.approx(0.2)
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_log_stability_info_when_stable(db, caplog):
    """A day-to-day top-N whose overlap is >= 0.5 logs at INFO, not WARNING."""
    import logging

    from techtrend.pipeline.score import CURRENT_SCORE_VERSION
    from techtrend.pipeline.stability import log_stability

    ids = {name: _insert_entity(db, name) for name in ("e1", "e2", "e3", "e4")}

    # Prior run's top-3: e1, e2, e3.
    _insert_score(db, ids["e1"], "2026-07-18", 0.9, CURRENT_SCORE_VERSION)
    _insert_score(db, ids["e2"], "2026-07-18", 0.8, CURRENT_SCORE_VERSION)
    _insert_score(db, ids["e3"], "2026-07-18", 0.7, CURRENT_SCORE_VERSION)
    # Today's top-3: e1, e2, e4 -- overlap {e1, e2} over union of 4 = 0.5.
    _insert_score(db, ids["e1"], "2026-07-19", 0.9, CURRENT_SCORE_VERSION)
    _insert_score(db, ids["e2"], "2026-07-19", 0.85, CURRENT_SCORE_VERSION)
    _insert_score(db, ids["e4"], "2026-07-19", 0.7, CURRENT_SCORE_VERSION)
    db.commit()

    with caplog.at_level(logging.INFO, logger="techtrend.pipeline.stability"):
        overlap = log_stability(db, date(2026, 7, 19), top_n=3)

    assert overlap == pytest.approx(0.5)
    assert not any(record.levelno == logging.WARNING for record in caplog.records)
    assert any(record.levelno == logging.INFO for record in caplog.records)


def test_score_entry_point_writes_scores_and_run_manifest(tmp_path, monkeypatch):
    """`python -m techtrend.score` against a fixture-populated DB writes
    scores rows and a run_manifest row with stage 'score'.
    """
    import sqlite3

    from techtrend.db import connection as db_connection

    db_path = tmp_path / "score-entry.db"
    monkeypatch.setattr(db_connection, "DEFAULT_DB_PATH", db_path)

    from techtrend import ingest, score

    assert ingest.main(["--fixture"]) == 0
    assert score.main([]) == 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    scores_count = conn.execute("SELECT COUNT(*) AS c FROM scores").fetchone()["c"]
    run_manifest_count = conn.execute(
        "SELECT COUNT(*) AS c FROM run_manifest WHERE stage = 'score'"
    ).fetchone()["c"]
    conn.close()

    assert scores_count >= 1
    assert run_manifest_count >= 1
