"""Jaccard rank-overlap stability metric (SCORE-05, D-12).

D-12: ship the 7-day-window-plus-Wilson-bound scorer with NO additional
damping in Phase 1 -- exponentially-weighted smoothing and any form of
rank-carries-over-from-yesterday memory are both explicitly rejected, the
latter specifically because it would make the displayed rank depend on the
prior run's rank, breaking the "scores are a pure function of (entities,
snapshots)" property that keeps re-scoring free. This module only MEASURES
day-to-day stability; it never smooths or damps anything.
"""

import logging

logger = logging.getLogger(__name__)


def rank_overlap(prev_top_n: set[int], curr_top_n: set[int]) -> float:
    """Jaccard index of two top-N entity-id sets.

    Both empty -> 1.0 (no movement to measure, never a divide-by-zero on
    an empty union).
    """
    if not prev_top_n and not curr_top_n:
        return 1.0
    union = prev_top_n | curr_top_n
    intersection = prev_top_n & curr_top_n
    return len(intersection) / len(union)


def _top_n_eligible_ids(conn, run_date_str: str, score_version: int, top_n: int) -> set[int]:
    rows = conn.execute(
        """
        SELECT entity_id FROM scores
        WHERE run_date = %s AND score_version = %s AND eligible = 1
        ORDER BY wilson_lower_bound DESC, entity_id ASC
        LIMIT %s
        """,
        (run_date_str, score_version, top_n),
    ).fetchall()
    return {row["entity_id"] for row in rows}


def _previous_run_date(conn, run_date_str: str, score_version: int) -> str | None:
    row = conn.execute(
        """
        SELECT DISTINCT run_date FROM scores
        WHERE score_version = %s AND run_date < %s
        ORDER BY run_date DESC
        LIMIT 1
        """,
        (score_version, run_date_str),
    ).fetchone()
    return row["run_date"] if row else None


def log_stability(conn, run_date, top_n: int) -> float:
    """Compute the Jaccard rank-overlap between the previous run's top-N
    eligible entities and this run's, and log it -- at WARNING when the
    value falls below 0.5, at INFO otherwise (SCORE-05 boundary).

    When there is no previous run to compare against (day one), `prev` is
    treated as the empty set -- an empty `curr` still yields 1.0, a
    non-empty `curr` yields 0.0 (nothing yet to have overlapped with).
    """
    from techtrend.pipeline.score import CURRENT_SCORE_VERSION

    run_date_str = run_date.isoformat() if hasattr(run_date, "isoformat") else str(run_date)
    curr = _top_n_eligible_ids(conn, run_date_str, CURRENT_SCORE_VERSION, top_n)

    prev_run_date = _previous_run_date(conn, run_date_str, CURRENT_SCORE_VERSION)
    prev = (
        _top_n_eligible_ids(conn, prev_run_date, CURRENT_SCORE_VERSION, top_n)
        if prev_run_date
        else set()
    )

    overlap = rank_overlap(prev, curr)
    level = logging.WARNING if overlap < 0.5 else logging.INFO
    logger.log(
        level,
        "stage=score stability=%.3f top_n=%d run_date=%s prev_run_date=%s",
        overlap,
        top_n,
        run_date_str,
        prev_run_date,
    )
    return overlap
