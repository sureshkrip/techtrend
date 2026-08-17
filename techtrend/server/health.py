"""Three-tier health escalation over run_manifest (D-16, HEALTH-02).

`health_status()` evaluates D-16's escalation order exactly:

1. **critical** -- the collector's own history has never once succeeded
   (an empty `run_manifest`, or one that holds only failed/zero_items
   collector rows), taking the distinct "never completed successfully"
   copy so a brand-new install reads as "still gathering data" rather than
   as a defect (D-08a).
2. **critical** -- the most recent collector-stage row recorded `failed`,
   or recorded `zero_items` while the trailing average item count over the
   last `zero_items_trailing_runs` collector runs is non-trivial (the
   Pitfall 1 floor check: a dead collector returns HTTP 200 with nothing,
   and the run "succeeds", so a trailing-average comparison is the only
   way that failure becomes visible). A trailing average of exactly zero
   never escalates -- a brand-new install would otherwise open on a red
   banner from day one.
3. **stale** -- the newest successful run (any stage, DASH-06 planner
   assumption) finished more than `staleness_hours` ago. Inclusive on the
   healthy side: exactly the threshold is still `normal`.
4. **normal** -- otherwise.

`error_detail` is truncated to 120 characters with a trailing ellipsis
before it ever reaches the render context; the untruncated text stays in
the log file only (T-01-31 mitigation).
"""

from datetime import UTC, datetime
from enum import StrEnum

import psycopg

from techtrend.server.queries import query_latest_run

_ERROR_DETAIL_TRUNCATE_LEN = 120

NEVER_COMPLETED_MESSAGE = (
    "GitHub collection has never completed successfully — no ranked data is available yet."
)


class HealthTier(StrEnum):
    normal = "normal"
    stale = "stale"
    critical = "critical"


def relative_time(dt: datetime, now: datetime) -> str:
    """Human relative-time phrasing: 'just now', '5 minutes ago',
    '2 hours ago', '3 days ago'. Never raises on a `dt` in the future --
    a negative delta is floored at 'just now'.
    """
    seconds = max(0.0, (now - dt).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = int(seconds // 3600)
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(seconds // 86400)
    return f"{days} day{'s' if days != 1 else ''} ago"


def _parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _truncate_error_detail(detail: str | None) -> str | None:
    if detail is None:
        return None
    if len(detail) <= _ERROR_DETAIL_TRUNCATE_LEN:
        return detail
    return detail[:_ERROR_DETAIL_TRUNCATE_LEN] + "..."


def _latest_collector_stage(
    conn: psycopg.Connection, status: str | None = None
) -> dict | None:
    """Most recent `collect:*` run_manifest row, optionally filtered to a status."""
    if status is None:
        return conn.execute(
            """
            SELECT * FROM run_manifest
            WHERE stage LIKE 'collect:%%'
            ORDER BY run_date DESC, started_at DESC
            LIMIT 1
            """
        ).fetchone()
    return conn.execute(
        """
        SELECT * FROM run_manifest
        WHERE stage LIKE 'collect:%%' AND status = %(status)s
        ORDER BY run_date DESC, started_at DESC
        LIMIT 1
        """,
        {"status": status},
    ).fetchone()


def _latest_score_stage(conn: psycopg.Connection) -> dict | None:
    """Most recent `score` run_manifest row, mirroring `_latest_collector_stage`
    (D-16/WR-01) -- the collect stage succeeding says nothing about whether the
    scores derived from it were ever written.
    """
    return conn.execute(
        """
        SELECT * FROM run_manifest
        WHERE stage = 'score'
        ORDER BY run_date DESC, started_at DESC
        LIMIT 1
        """
    ).fetchone()


def _trailing_average_non_trivial(conn: psycopg.Connection, trailing_runs: int) -> bool:
    """True when the average item_count across the last `trailing_runs`
    collector runs (most recent first, including the current one) is
    greater than zero -- the zero_items floor check (Pitfall 1).
    """
    rows = conn.execute(
        """
        SELECT item_count FROM run_manifest
        WHERE stage LIKE 'collect:%%'
        ORDER BY run_date DESC, started_at DESC
        LIMIT %(trailing_runs)s
        """,
        {"trailing_runs": trailing_runs},
    ).fetchall()
    if not rows:
        return False
    counts = [row["item_count"] or 0 for row in rows]
    return (sum(counts) / len(counts)) > 0


def _failure_message(relative: str) -> str:
    # relative_time() already returns a full phrase including "ago" (e.g.
    # "3 days ago"), matching the Copywriting Contract's rendered example --
    # do not append a second literal " ago" here (that produced a
    # double "ago ago" bug caught by test_health.py).
    return f"GitHub collection failed on the last run — showing data from {relative}."


def _stale_message(relative: str) -> str:
    return f"Data may be out of date — last successful run was {relative}."


def has_successful_collector_run(conn: psycopg.Connection) -> bool:
    """True if at least one `collect:*` run_manifest row has ever recorded
    `status = 'success'` (V2/D-08a). This is the same predicate
    `health_status()` uses internally to choose `NEVER_COMPLETED_MESSAGE`,
    exposed publicly so the dashboard route can distinguish "no run has
    completed yet" from "a run completed but nothing is eligible to rank
    yet" -- the two empty states table.html must render distinct, honest
    copy for.
    """
    return _latest_collector_stage(conn, status="success") is not None


def health_status(conn: psycopg.Connection, config, now: datetime) -> dict:
    """Return `{'tier': HealthTier, 'message': str, 'detail': str | None}`."""
    staleness_hours = config.tunables.staleness_hours
    zero_items_trailing_runs = config.tunables.zero_items_trailing_runs

    latest_successful_collector = _latest_collector_stage(conn, status="success")

    if latest_successful_collector is None:
        return {"tier": HealthTier.critical, "message": NEVER_COMPLETED_MESSAGE, "detail": None}

    good_relative = relative_time(_parse_iso(latest_successful_collector["finished_at"]), now)

    latest_collector = _latest_collector_stage(conn)
    if latest_collector is not None:
        if latest_collector["status"] == "failed":
            return {
                "tier": HealthTier.critical,
                "message": _failure_message(good_relative),
                "detail": _truncate_error_detail(latest_collector["error_detail"]),
            }
        if latest_collector["status"] == "zero_items" and _trailing_average_non_trivial(
            conn, zero_items_trailing_runs
        ):
            return {
                "tier": HealthTier.critical,
                "message": _failure_message(good_relative),
                "detail": _truncate_error_detail(latest_collector["error_detail"]),
            }

    # A successful collect stage says nothing about whether the score stage
    # that runs afterward actually produced a ranking -- check it separately
    # (WR-01/D-16) so a failed score run is never masked by a healthy collect.
    latest_score = _latest_score_stage(conn)
    if latest_score is not None and latest_score["status"] == "failed":
        return {
            "tier": HealthTier.critical,
            "message": _failure_message(good_relative),
            "detail": _truncate_error_detail(latest_score["error_detail"]),
        }

    latest_any_success = query_latest_run(conn)
    if latest_any_success is not None:
        display_dt = _parse_iso(latest_any_success["finished_at"])
    else:
        display_dt = _parse_iso(latest_successful_collector["finished_at"])
    display_relative = relative_time(display_dt, now)
    hours_since = max(0.0, (now - display_dt).total_seconds()) / 3600

    if hours_since > staleness_hours:
        return {
            "tier": HealthTier.stale,
            "message": _stale_message(display_relative),
            "detail": None,
        }

    return {
        "tier": HealthTier.normal,
        "message": f"Last successful run: {display_relative}.",
        "detail": None,
    }
