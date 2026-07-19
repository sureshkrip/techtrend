"""Confidence-bounded velocity scoring (SCORE-01..SCORE-05).

`rescore_all` is a pure function of (entities, snapshots): it never reads
the previous run's ranking, which is what keeps re-scoring free and
reproducible (D-12, DATA-03). The absolute floor (D-10/SCORE-03) is checked
BEFORE the Wilson bound is ever computed for an entity -- inverting that
order reintroduces the exact small-number-noise defect 01-RESEARCH.md
validated against: a 2->10 entity's raw Wilson bound (~0.490) is higher
than a 4,000->4,300 entity's (~0.0625), so the floor -- not the bound --
is what excludes it from ranking at all.

No network I/O anywhere in this module; scoring reads only `entities` and
`snapshots`.
"""

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta

from techtrend.pipeline.normalize import momentum_for_source

logger = logging.getLogger(__name__)

# 95% confidence Wilson score interval.
Z_SCORE_95 = 1.96

# Bumped manually whenever the formula in score_entity()/wilson_lower_bound()
# changes. Old-version rows are left in place (never deleted) so a formula
# regression stays comparable against the prior version's output (T-01-21).
CURRENT_SCORE_VERSION = 1


@dataclass
class WindowGain:
    """One entity's trailing-window star movement.

    `window_days_actual` records the ACTUAL span of days observed, which
    may be fewer than the configured window for a fresh entity -- recording
    the true span (rather than substituting the configured value) is what
    keeps a 1-day observation distinguishable downstream from a full 7-day
    one.
    """

    stars_gained: int
    stars_total: int
    window_days_actual: int


def wilson_lower_bound(successes: int, n: int, z: float = Z_SCORE_95) -> float:
    """Wilson score interval lower bound. Returns 0.0 for n <= 0 rather than
    raising ZeroDivisionError, and the result is floored at 0.0 so a
    negative value can never be returned.

    `phat` is clamped to [0.0, 1.0] before use -- an out-of-range successes
    count (e.g. negative, from a caller that skipped score_entity's own
    clamp) would otherwise drive the radicand negative and raise
    ValueError: math domain error from math.sqrt.
    """
    if n <= 0:
        return 0.0
    phat = max(0.0, min(1.0, successes / n))
    denom = 1 + z**2 / n
    center = phat + z**2 / (2 * n)
    radicand = max(0.0, (phat * (1 - phat) + z**2 / (4 * n)) / n)
    margin = z * math.sqrt(radicand)
    return max(0.0, (center - margin) / denom)


def score_entity(stars_gained: int, stars_total: int, floor: int) -> tuple[bool, float]:
    """Returns (eligible, wilson_lower_bound).

    The floor check runs FIRST, before any bound is computed -- this
    ordering is the entire mitigation for small-number noise (SCORE-03).
    Integers are compared directly; no float coercion happens before the
    floor comparison. `successes` is clamped to `min(stars_gained,
    stars_total)` so the proportion can never exceed 1.0.
    """
    if stars_gained < floor or stars_total <= 0:
        return False, 0.0
    n = stars_total
    successes = min(stars_gained, n)
    return True, wilson_lower_bound(successes, n)


def compute_window_gain(conn, entity_id: int, window_days: int) -> WindowGain:
    """Reads every `stars` snapshot row for `entity_id`, trims to the
    trailing `window_days` relative to that entity's own most recent
    snapshot, and returns the gain across whatever range is actually
    available.

    Anchoring the trailing window on the entity's own latest snapshot
    (rather than on wall-clock "now") is what keeps this function a pure
    function of the `snapshots` table alone -- re-running it never depends
    on when it happens to be invoked (SCORE-04 concurrency/purity).

    Returns zeros with `window_days_actual` of 0 when the entity has no
    snapshot rows.
    """
    rows = conn.execute(
        """
        SELECT collected_at, metric_value FROM snapshots
        WHERE entity_id = ? AND metric_name = 'stars'
        ORDER BY collected_at ASC
        """,
        (entity_id,),
    ).fetchall()

    if not rows:
        return WindowGain(stars_gained=0, stars_total=0, window_days_actual=0)

    latest_date = date.fromisoformat(rows[-1]["collected_at"])
    window_start = latest_date - timedelta(days=max(window_days - 1, 0))

    in_window = [r for r in rows if date.fromisoformat(r["collected_at"]) >= window_start]
    values = [r["metric_value"] for r in in_window]

    stars_gained = max(values) - min(values)
    stars_total = values[-1]

    earliest_in_window = date.fromisoformat(in_window[0]["collected_at"])
    window_days_actual = (latest_date - earliest_in_window).days

    return WindowGain(
        stars_gained=stars_gained,
        stars_total=stars_total,
        window_days_actual=window_days_actual,
    )


def rescore_all(conn, config, run_date) -> int:
    """Deletes existing rows for CURRENT_SCORE_VERSION at every run_date,
    then re-scores every non-dormant entity and writes one `scores` row per
    entity (eligible or not) keyed on (entity_id, run_date, score_version).

    Rows at other score_version values are left untouched (T-01-21). Reads
    only `entities` and `snapshots` -- no network I/O, and no read of the
    previous run's ranking, which is what keeps re-scoring free (D-12).

    Returns the number of scores rows written.
    """
    run_date_str = run_date.isoformat() if hasattr(run_date, "isoformat") else str(run_date)
    window_days = config.tunables.window_days
    floor = config.tunables.window_gain_floor

    conn.execute("DELETE FROM scores WHERE score_version = ?", (CURRENT_SCORE_VERSION,))

    entities = conn.execute(
        "SELECT id, source FROM entities WHERE dormant_at IS NULL ORDER BY id"
    ).fetchall()

    written = 0
    for entity in entities:
        gain = compute_window_gain(conn, entity["id"], window_days)
        momentum_gain, momentum_total = momentum_for_source(
            entity["source"], gain.stars_gained, gain.stars_total
        )
        eligible, bound = score_entity(momentum_gain, momentum_total, floor)

        conn.execute(
            """
            INSERT INTO scores (
                entity_id, run_date, score_version, stars_gained,
                window_days, wilson_lower_bound, eligible
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity["id"],
                run_date_str,
                CURRENT_SCORE_VERSION,
                gain.stars_gained,
                gain.window_days_actual,
                bound,
                int(eligible),
            ),
        )
        written += 1

    conn.commit()
    logger.info("stage=score entities=%d run_date=%s", written, run_date_str)
    return written
