"""Read-only SQL for the dashboard.

Every function here issues SELECT statements only -- the dashboard is
strictly read-only (D-17) and must never write a row.

`sort` never reaches SQL construction as raw text: it maps through the
`_SORT_ORDER_BY` allow-dict to a fixed ORDER BY fragment, defaulting to
`velocity` on any unrecognized input (T-01-06).
"""

import sqlite3

# scores is empty until plan 01-04 lands, so the LEFT JOIN + entities.id
# tiebreak matter -- the skeleton must still render rows with no scores yet.
_SORT_ORDER_BY: dict[str, str] = {
    "velocity": "scores.wilson_lower_bound DESC NULLS LAST, entities.id ASC",
    "stars_gained": "scores.stars_gained DESC NULLS LAST, entities.id ASC",
    "stars": "stars_total DESC NULLS LAST, entities.id ASC",
    "name": "entities.full_name ASC",
}
DEFAULT_SORT = "velocity"

_QUERY_RANKED_SQL = """
    SELECT
        entities.id AS entity_id,
        entities.full_name,
        entities.url,
        entities.homepage,
        entities.docs_url,
        entities.docs_url_kind,
        scores.wilson_lower_bound,
        scores.stars_gained,
        scores.window_days,
        (
            SELECT snapshots.metric_value
            FROM snapshots
            WHERE snapshots.entity_id = entities.id
              AND snapshots.metric_name = 'stars'
            ORDER BY snapshots.collected_at DESC
            LIMIT 1
        ) AS stars_total
    FROM entities
    LEFT JOIN scores ON scores.entity_id = entities.id
    ORDER BY {order_by}
"""


def query_ranked(conn: sqlite3.Connection, sort: str = DEFAULT_SORT) -> list[sqlite3.Row]:
    """Return every entity LEFT JOINed to scores, ordered by the requested sort.

    `scores` is empty until plan 01-04 lands; the LEFT JOIN and the
    deterministic `entities.id ASC` tiebreak keep row order stable so the
    skeleton renders correctly before any scoring exists.
    """
    order_by = _SORT_ORDER_BY.get(sort, _SORT_ORDER_BY[DEFAULT_SORT])
    sql = _QUERY_RANKED_SQL.format(order_by=order_by)
    return conn.execute(sql).fetchall()


def query_latest_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Return the most recent successful run_manifest row, or None if the table is empty."""
    row = conn.execute(
        """
        SELECT *
        FROM run_manifest
        WHERE status = 'success'
        ORDER BY finished_at DESC, started_at DESC
        LIMIT 1
        """
    ).fetchone()
    return row
