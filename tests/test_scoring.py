"""Velocity scoring tests (SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05).

Encodes the load-bearing finding from 01-RESEARCH.md Pattern 3: the Wilson
lower bound ALONE does not solve small-number noise -- a 2->10 star entity's
raw bound (~0.490) is HIGHER than a 4,000->4,300 entity's (~0.0625). Only the
absolute floor (D-10/SCORE-03) together with the Wilson bound (D-11/SCORE-02)
produce the intended ordering; the floor must run first, before the bound is
ever consulted, and that ordering is asserted directly below, not just
documented.

No live network call -- snapshot series are constructed directly as rows in
the `db` fixture's temp SQLite file (CLAUDE.md testing philosophy).
"""

from datetime import date

import pytest

from techtrend.config import Config, Tunables


def _insert_entity(conn, native_id, full_name=None, dormant=False):
    full_name = full_name or f"owner/{native_id}"
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, discovery_method,
            admitted_at, last_seen_at, dormant_at
        ) VALUES (
            'github', :native_id, :full_name, :url, 'seed',
            '2026-07-01T00:00:00Z', '2026-07-19T00:00:00Z', :dormant_at
        )
        """,
        {
            "native_id": native_id,
            "full_name": full_name,
            "url": f"https://github.com/{full_name}",
            "dormant_at": "2026-07-01T00:00:00Z" if dormant else None,
        },
    )
    return conn.execute(
        "SELECT id FROM entities WHERE source_native_id = ?", (native_id,)
    ).fetchone()["id"]


def _insert_snapshot(conn, entity_id, collected_at, value, source_kind="observed"):
    conn.execute(
        """
        INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value, source_kind)
        VALUES (?, ?, 'stars', ?, ?)
        """,
        (entity_id, collected_at, value, source_kind),
    )


def _seed_series(conn, native_id, start_value, end_value, start_date, end_date):
    """Two-point snapshot series: (start_date, start_value) -> (end_date, end_value)."""
    entity_id = _insert_entity(conn, native_id)
    _insert_snapshot(conn, entity_id, start_date.isoformat(), start_value)
    _insert_snapshot(conn, entity_id, end_date.isoformat(), end_value)
    conn.commit()
    return entity_id


def _config(window_days=7, floor=25, stability_top_n=25):
    return Config(
        tunables=Tunables(
            window_days=window_days,
            window_gain_floor=floor,
            stability_top_n=stability_top_n,
        )
    )


def test_small_number_noise_excluded(db):
    """CONTEXT.md's hand-named assertion, as an end-to-end ranking check
    rather than a unit comparison of two floats -- a test that only compared
    bounds would pass even with the floor removed, which is precisely the
    regression this test exists to catch.
    """
    from techtrend.pipeline.score import rescore_all

    small_id = _seed_series(db, "small", 2, 10, date(2026, 7, 13), date(2026, 7, 19))
    large_id = _seed_series(db, "large", 4000, 4300, date(2026, 7, 13), date(2026, 7, 19))

    rescore_all(db, _config(), date(2026, 7, 19))

    eligible_ids = {
        row["entity_id"]
        for row in db.execute("SELECT entity_id FROM scores WHERE eligible = 1").fetchall()
    }
    assert small_id not in eligible_ids
    assert large_id in eligible_ids


def test_floor_excludes_before_wilson(db):
    """With the floor disabled, the small entity's raw Wilson bound (~0.490)
    beats the large entity's (~0.0625) and it ranks first. With the floor
    enabled at its configured value, the small entity is absent entirely.
    The floor value flows through config.tunables.window_gain_floor, never
    a hardcoded constant.
    """
    from techtrend.pipeline.score import rescore_all

    small_id = _seed_series(db, "small", 2, 10, date(2026, 7, 13), date(2026, 7, 19))
    large_id = _seed_series(db, "large", 4000, 4300, date(2026, 7, 13), date(2026, 7, 19))

    rescore_all(db, _config(floor=0), date(2026, 7, 19))
    top = db.execute(
        "SELECT entity_id FROM scores WHERE eligible = 1 "
        "ORDER BY wilson_lower_bound DESC, entity_id ASC LIMIT 1"
    ).fetchone()
    assert top["entity_id"] == small_id

    rescore_all(db, _config(floor=25), date(2026, 7, 19))
    eligible_ids = {
        row["entity_id"]
        for row in db.execute("SELECT entity_id FROM scores WHERE eligible = 1").fetchall()
    }
    assert small_id not in eligible_ids
    assert large_id in eligible_ids


def test_partial_window_gain(db):
    """A fresh entity with fewer than window_days of history records the
    ACTUAL span observed, not the configured window_days -- substituting the
    configured value would silently overstate confidence in a 1- or 2-day
    observation.
    """
    from techtrend.pipeline.score import compute_window_gain

    entity_id = _seed_series(db, "fresh", 100, 130, date(2026, 7, 17), date(2026, 7, 19))

    gain = compute_window_gain(db, entity_id, window_days=7)

    assert gain.stars_gained == 30
    assert gain.stars_total == 130
    assert gain.window_days_actual == 2


def test_window_gain_uses_last_minus_first_not_max_minus_min(db):
    """WR-03 regression: a window with an early spike that later partially
    reverses ([100, 150, 90]) must report the true net change (90 - 100 =
    -10, a loss), not the peak-to-trough range (150 - 90 = 60, a large
    apparent gain) -- the pre-fix max()-min() computation would incorrectly
    report a gain for a repo that actually lost stars over the window.
    """
    from techtrend.pipeline.score import compute_window_gain

    entity_id = _insert_entity(db, "spiky")
    _insert_snapshot(db, entity_id, "2026-07-13", 100)
    _insert_snapshot(db, entity_id, "2026-07-16", 150)
    _insert_snapshot(db, entity_id, "2026-07-19", 90)
    db.commit()

    gain = compute_window_gain(db, entity_id, window_days=7)

    assert gain.stars_gained == -10
    assert gain.stars_total == 90


def test_window_gain_non_monotonic_series_does_not_falsely_clear_the_floor(db):
    """The same non-monotonic scenario end-to-end through rescore_all: a
    net-losing entity must not be pushed over the SCORE-03 floor by the
    max-min defect, even though its peak-to-trough range (60) would have
    cleared a floor of 25.
    """
    from techtrend.pipeline.score import rescore_all

    entity_id = _insert_entity(db, "spiky")
    _insert_snapshot(db, entity_id, "2026-07-13", 100)
    _insert_snapshot(db, entity_id, "2026-07-16", 150)
    _insert_snapshot(db, entity_id, "2026-07-19", 90)
    db.commit()

    rescore_all(db, _config(floor=25), date(2026, 7, 19))

    row = db.execute(
        "SELECT eligible, stars_gained FROM scores WHERE entity_id = ?", (entity_id,)
    ).fetchone()
    assert row["stars_gained"] == -10
    assert row["eligible"] == 0


def test_floor_inclusive_at_exact_value():
    """The floor is inclusive at exactly the configured value (D-10)."""
    from techtrend.pipeline.score import score_entity

    eligible_at_floor, _ = score_entity(25, 75, 25)
    eligible_below_floor, _ = score_entity(24, 75, 25)

    assert eligible_at_floor is True
    assert eligible_below_floor is False


def test_wilson_zero_n_returns_zero():
    """wilson_lower_bound never raises ZeroDivisionError for n <= 0."""
    from techtrend.pipeline.score import wilson_lower_bound

    assert wilson_lower_bound(0, 0) == 0.0
    assert wilson_lower_bound(5, 0) == 0.0
    assert wilson_lower_bound(5, -1) == 0.0


def test_wilson_never_negative():
    """The bound is floored at 0.0 for any input."""
    from techtrend.pipeline.score import wilson_lower_bound

    assert wilson_lower_bound(0, 1) >= 0.0
    assert wilson_lower_bound(0, 5) >= 0.0
    assert wilson_lower_bound(1, 1_000_000) >= 0.0


def test_wilson_clamps_successes_to_n():
    """When stars_gained equals or exceeds stars_total, successes is clamped
    to n so the computed proportion never exceeds 1.0 and no exception is
    raised.
    """
    from techtrend.pipeline.score import score_entity

    eligible_equal, bound_equal = score_entity(50, 50, 25)
    eligible_over, bound_over = score_entity(100, 50, 25)

    assert eligible_equal is True
    assert 0.0 <= bound_equal <= 1.0
    assert eligible_over is True
    assert 0.0 <= bound_over <= 1.0


def test_identical_inputs_tie_break_by_entity_id(db):
    """Two entities with identical (gained, total) receive identical Wilson
    bounds and rank adjacently, broken deterministically by entity_id
    ascending.
    """
    from techtrend.pipeline.score import rescore_all

    first_id = _seed_series(db, "twin-a", 50, 75, date(2026, 7, 13), date(2026, 7, 19))
    second_id = _seed_series(db, "twin-b", 50, 75, date(2026, 7, 13), date(2026, 7, 19))

    rescore_all(db, _config(), date(2026, 7, 19))

    rows = db.execute(
        "SELECT entity_id, wilson_lower_bound FROM scores WHERE eligible = 1 "
        "ORDER BY wilson_lower_bound DESC, entity_id ASC"
    ).fetchall()

    assert len(rows) == 2
    assert rows[0]["wilson_lower_bound"] == pytest.approx(rows[1]["wilson_lower_bound"])
    assert rows[0]["entity_id"] < rows[1]["entity_id"]
    assert {rows[0]["entity_id"], rows[1]["entity_id"]} == {first_id, second_id}


def test_entity_with_no_snapshots_is_ineligible(db):
    """An entity with zero snapshot rows yields window_days 0, stars_gained
    0, eligible 0, and is excluded without raising.
    """
    from techtrend.pipeline.score import compute_window_gain, rescore_all

    entity_id = _insert_entity(db, "no-snapshots")
    db.commit()

    gain = compute_window_gain(db, entity_id, window_days=7)
    assert gain.stars_gained == 0
    assert gain.stars_total == 0
    assert gain.window_days_actual == 0

    rescore_all(db, _config(), date(2026, 7, 19))

    row = db.execute("SELECT eligible FROM scores WHERE entity_id = ?", (entity_id,)).fetchone()
    assert row["eligible"] == 0


def test_ineligible_excluded_not_sorted_last(db):
    """Ineligible entities are excluded from the ranked list entirely,
    rather than present but sorted to the bottom of it.
    """
    from techtrend.pipeline.score import rescore_all

    eligible_id = _seed_series(db, "big-mover", 4000, 4300, date(2026, 7, 13), date(2026, 7, 19))
    ineligible_id = _seed_series(db, "quiet", 2, 10, date(2026, 7, 13), date(2026, 7, 19))

    rescore_all(db, _config(), date(2026, 7, 19))

    ranked_ids = [
        row["entity_id"]
        for row in db.execute(
            "SELECT entity_id FROM scores WHERE eligible = 1 "
            "ORDER BY wilson_lower_bound DESC, entity_id ASC"
        ).fetchall()
    ]

    assert ranked_ids == [eligible_id]
    assert ineligible_id not in ranked_ids


def test_score_versions_coexist(db):
    """A scores row at a different score_version is left untouched by a
    re-score at CURRENT_SCORE_VERSION -- both versions coexist, keyed by
    (entity_id, run_date, score_version), so a formula regression stays
    comparable against the prior version.
    """
    from techtrend.pipeline.score import CURRENT_SCORE_VERSION, rescore_all

    entity_id = _seed_series(db, "versioned", 4000, 4300, date(2026, 7, 13), date(2026, 7, 19))

    other_version = CURRENT_SCORE_VERSION + 1
    db.execute(
        """
        INSERT INTO scores (
            entity_id, run_date, score_version, stars_gained,
            window_days, wilson_lower_bound, eligible
        ) VALUES (?, '2026-07-19', ?, 300, 6, 0.0625, 1)
        """,
        (entity_id, other_version),
    )
    db.commit()

    rescore_all(db, _config(), date(2026, 7, 19))

    other_count = db.execute(
        "SELECT COUNT(*) AS c FROM scores WHERE score_version = ?", (other_version,)
    ).fetchone()["c"]
    current_count = db.execute(
        "SELECT COUNT(*) AS c FROM scores WHERE score_version = ?", (CURRENT_SCORE_VERSION,)
    ).fetchone()["c"]

    assert other_count == 1
    assert current_count == 1


def test_wilson_bounds_match_research_worked_examples():
    """The three cases computed by hand in 01-RESEARCH.md Pattern 3."""
    from techtrend.pipeline.score import wilson_lower_bound

    assert wilson_lower_bound(8, 10) == pytest.approx(0.490, abs=1e-3)
    assert wilson_lower_bound(25, 75) == pytest.approx(0.237, abs=1e-3)
    assert wilson_lower_bound(300, 4300) == pytest.approx(0.0625, abs=1e-3)
