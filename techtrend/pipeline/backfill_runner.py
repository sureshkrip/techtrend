"""First-sight backfill trigger, provenance-tagged snapshot writes, and honest
per-repo status bookkeeping (D-07, D-08, D-08a).

Invoked from `techtrend/ingest.py` AFTER the live collection stage completes,
and inside its own exception guard there -- backfill failure must never
block or delay current data collection, and must never roll back observed
snapshots (D-08). Every point is written through `write_snapshot()` with
`source_kind='backfill'`, the same table and function observed collection
uses, so the scorer reads one uniform series with no special-casing (D-07)
and a re-run is idempotent for free via the existing `(entity_id,
collected_at, metric_name)` uniqueness constraint (DATA-05).

Under the D-08a graceful-degradation decision, a permission-denied
('blocked') repo is recorded honestly and is never retried -- retrying a
platform restriction that can never succeed would burn rate-limit quota
every run for nothing (T-01-24). COLL-02/D-05/D-06 are therefore satisfied
in DEGRADED form only for repos the operator does not own or collaborate
on; this module's `run_manifest` row is the audit trail of exactly how much.
"""

import logging
from datetime import UTC, date, datetime

from techtrend.collectors.backfill import (
    BackfillBlocked,
    BackfillTruncated,
    sample_stargazer_history,
)
from techtrend.config import Config
from techtrend.pipeline.orchestrator import record_stage
from techtrend.pipeline.snapshot import write_snapshot

logger = logging.getLogger(__name__)

# D-08 retry set: 'pending' has never been attempted, 'failed'/'truncated'
# are retried next run. 'complete' is done; 'blocked' is a permanent denial
# and is deliberately excluded -- see run_backfill()'s docstring.
_RETRY_STATUSES = ("pending", "failed", "truncated")
_SKIPPED_STATUSES = ("complete", "blocked")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _select_backfill_candidates(conn) -> list[dict]:
    """Entities due for a backfill attempt this run (D-08)."""
    placeholders = ",".join("%s" for _ in _RETRY_STATUSES)
    rows = conn.execute(
        f"SELECT id, full_name, backfill_status FROM entities "
        f"WHERE backfill_status IN ({placeholders})",
        _RETRY_STATUSES,
    ).fetchall()
    return [dict(row) for row in rows]


def _count_skipped(conn) -> int:
    placeholders = ",".join("%s" for _ in _SKIPPED_STATUSES)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM entities WHERE backfill_status IN ({placeholders})",
        _SKIPPED_STATUSES,
    ).fetchone()
    return row["n"]


def _latest_observed_stars(conn, entity_id: int) -> int | None:
    """The most recent observed star count, used to anchor the sampled
    curve. Backfill runs after live collection in the same run (D-08), so a
    first-sight entity should always have one by the time this executes.
    """
    row = conn.execute(
        """
        SELECT metric_value FROM snapshots
        WHERE entity_id = %s AND metric_name = 'stars' AND source_kind = 'observed'
        ORDER BY collected_at DESC LIMIT 1
        """,
        (entity_id,),
    ).fetchone()
    return row["metric_value"] if row is not None else None


def _set_backfill_status(
    conn, entity_id: int, status: str, backfilled_at: str | None = None
) -> None:
    conn.execute(
        "UPDATE entities SET backfill_status = %s, "
        "backfilled_at = COALESCE(%s, backfilled_at) WHERE id = %s",
        (status, backfilled_at, entity_id),
    )


def run_backfill(conn, client, config: Config, run_date: date) -> dict[str, int]:
    """Attempt backfill for every entity in the D-08 retry set.

    Never raises -- a per-entity failure (whatever its cause) is caught,
    logged, and recorded as that entity's 'failed' status so one bad repo
    can never take down the stage, the run, or its exit code. Returns
    counts keyed 'completed', 'blocked', 'failed', 'truncated', 'skipped'.
    """
    counts = {"completed": 0, "blocked": 0, "failed": 0, "truncated": 0, "skipped": 0}
    started_at = _now_iso()
    request_cap = config.tunables.backfill_request_cap
    lookback_days = config.tunables.backfill_lookback_days

    candidates = _select_backfill_candidates(conn)
    counts["skipped"] = _count_skipped(conn)

    for entity in candidates:
        entity_id = entity["id"]
        full_name = entity["full_name"]
        stars_total = _latest_observed_stars(conn, entity_id)
        if stars_total is None:
            # No observed snapshot yet to anchor the sample against --
            # retry next run once live collection has written one.
            counts["failed"] += 1
            _set_backfill_status(conn, entity_id, "failed")
            logger.warning(
                "stage=backfill:github repo=%s status=failed "
                "note=no observed stars snapshot to anchor backfill",
                full_name,
            )
            continue

        try:
            outcome = sample_stargazer_history(
                client, full_name, stars_total, request_cap, lookback_days
            )
        except BackfillBlocked:
            counts["blocked"] += 1
            _set_backfill_status(conn, entity_id, "blocked")
            logger.info(
                "stage=backfill:github repo=%s status=blocked "
                "note=permission denied by GitHub, will not be retried",
                full_name,
            )
            continue
        except Exception as exc:  # noqa: BLE001 - one bad repo must not abort the stage
            counts["failed"] += 1
            _set_backfill_status(conn, entity_id, "failed")
            logger.warning(
                "stage=backfill:github repo=%s status=failed error=%s",
                full_name,
                exc,
            )
            continue

        for collected_at, cumulative_stars in outcome.points:
            write_snapshot(
                conn,
                entity_id,
                collected_at,
                "stars",
                cumulative_stars,
                source_kind="backfill",
            )

        if isinstance(outcome, BackfillTruncated):
            counts["truncated"] += 1
            _set_backfill_status(conn, entity_id, "truncated")
        else:
            counts["completed"] += 1
            _set_backfill_status(conn, entity_id, "complete", backfilled_at=_now_iso())

    conn.commit()
    finished_at = _now_iso()

    # The stage row records the run's actual sweep, never a flat success --
    # under D-08a the blocked/failed counts are the honest measure of how
    # much of COLL-02 this run achieved, not a pass/fail bit.
    stage_status = "zero_items" if not candidates else "success"
    error_detail = (
        f"blocked={counts['blocked']} failed={counts['failed']} "
        f"truncated={counts['truncated']} skipped={counts['skipped']}"
    )
    record_stage(
        conn,
        run_date.isoformat(),
        "backfill:github",
        stage_status,
        item_count=counts["completed"],
        error_detail=error_detail,
        started_at=started_at,
        finished_at=finished_at,
    )
    conn.commit()

    logger.info(
        "stage=backfill:github completed=%d blocked=%d failed=%d truncated=%d skipped=%d",
        counts["completed"],
        counts["blocked"],
        counts["failed"],
        counts["truncated"],
        counts["skipped"],
    )
    return counts
