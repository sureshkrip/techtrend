"""Read-only SQL for the dashboard.

Every function here issues SELECT statements only -- the dashboard is
strictly read-only (D-17) and must never write a row.

`sort` never reaches SQL construction as raw text: it maps through the
`SORT_KEYS` allow-dict to a fixed ORDER BY fragment, defaulting to
`velocity` on any unrecognized input (T-01-06/T-01-29).

`query_ranked` filters to `scores.score_version = CURRENT_SCORE_VERSION AND
scores.eligible = 1` -- an unfiltered join would surface stale rows from a
prior score formula version and the exact small-number-noise repos the
SCORE-03 floor exists to suppress (a 2-to-10-star repo would otherwise
reappear on the dashboard the floor was designed to keep off it).

It also pins to the single most recent `run_date` written for that
`score_version`. `scores` carries `PRIMARY KEY (entity_id, run_date,
score_version)` -- one row per entity per run_date -- and
`pipeline/score.py::rescore_all` deletes every row at `CURRENT_SCORE_VERSION`
before writing the new run_date's rows in the same transaction, so under
normal operation only one run_date is ever present per score_version at a
time. Pinning to `MAX(run_date)` matches that write pattern exactly and is
defense-in-depth against any row set that (via a test fixture, a crash
between versions, or a future change to `rescore_all`) leaves more than one
run_date behind: without it, an entity with `scores` rows from two different
run_dates renders as two separate table rows instead of one.

`query_ranked` also LEFT JOINs `enrichments` (never JOIN) so an enrichment
cap-overflow or fetch failure never removes an already-ranked row (ENR-06),
and accepts an optional `section` filter for the sidebar (DASH-02/D-11) --
bound as a SQL parameter, never interpolated.
"""

import sqlite3

from techtrend.pipeline.score import CURRENT_SCORE_VERSION

# Allowed `sort` query-param values mapped to fixed ORDER BY fragments.
# Every fragment ends with a deterministic `entities.id ASC` tiebreak so
# identical requests always produce byte-identical row order (DASH-03
# adjacency) -- ties never reshuffle between requests.
SORT_KEYS: dict[str, str] = {
    "velocity": "scores.wilson_lower_bound DESC, entities.id ASC",
    "stars": "stars_total DESC, entities.id ASC",
    "gained": "scores.stars_gained DESC, entities.id ASC",
    "name": "entities.full_name ASC, entities.id ASC",
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
        enrichments.summary_line_1,
        enrichments.summary_line_2,
        enrichments.section,
        enrichments.low_confidence,
        enrichments.status AS enrichment_status,
        (
            SELECT snapshots.metric_value
            FROM snapshots
            WHERE snapshots.entity_id = entities.id
              AND snapshots.metric_name = 'stars'
            ORDER BY snapshots.collected_at DESC
            LIMIT 1
        ) AS stars_total
    FROM entities
    JOIN scores ON scores.entity_id = entities.id
    LEFT JOIN enrichments ON enrichments.entity_id = entities.id
        AND enrichments.computed_at = (
            SELECT MAX(e2.computed_at) FROM enrichments AS e2
            WHERE e2.entity_id = entities.id
        )
    WHERE scores.score_version = :score_version
      AND scores.eligible = 1
      AND scores.run_date = (
          SELECT MAX(latest.run_date)
          FROM scores AS latest
          WHERE latest.score_version = :score_version
      )
      {section_filter}
    ORDER BY {order_by}
"""


def query_ranked(
    conn: sqlite3.Connection, sort: str = DEFAULT_SORT, section: str | None = None
) -> tuple[list[sqlite3.Row], str]:
    """Return every eligible, current-score-version entity, ordered by the
    requested sort, plus the sort key actually applied.

    An unrecognized `sort` value falls back to `DEFAULT_SORT` rather than
    raising or reaching SQL unfiltered. The returned `applied_sort` reflects
    reality -- the template renders its active-sort glyph against the sort
    that actually ran, not the one that was requested.

    `enrichments` is LEFT JOINed (not JOINed) on the same MAX(computed_at)
    correlated-subquery "current row" idiom `query_partial_history_count`
    already uses for `scores.run_date` -- an eligible entity with no
    enrichments row (never enriched, capped, or a fetch_failed tombstone)
    must still appear in the result set with null summary/section fields,
    never be silently dropped (ENR-06/D-10, DASH-02 boundary).

    `section`, when given, narrows to rows whose current enrichment's
    `section` matches -- bound as a SQL parameter (`:section`), never
    interpolated as raw text, matching the discipline `SORT_KEYS` already
    enforces for `sort` (T-01-06/T-01-29, T-02-14). An unenriched row (null
    section) never matches a specific section filter and only appears under
    the default `section=None` ("All") view (D-13).
    """
    applied_sort = sort if sort in SORT_KEYS else DEFAULT_SORT
    order_by = SORT_KEYS[applied_sort]
    section_filter = "AND enrichments.section = :section" if section else ""
    sql = _QUERY_RANKED_SQL.format(order_by=order_by, section_filter=section_filter)
    params: dict[str, object] = {"score_version": CURRENT_SCORE_VERSION}
    if section:
        params["section"] = section
    rows = conn.execute(sql, params).fetchall()
    return rows, applied_sort


def query_section_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Per-section counts for the sidebar (DASH-02/D-11), pinned to the same
    MAX(run_date)/eligible=1/current-score-version seam as query_ranked, so
    sidebar counts never drift from what the table actually renders.

    Uses a JOIN (not LEFT JOIN) and excludes null sections -- an unenriched
    entity contributes to no section's count, matching D-13 (unenriched
    items only ever appear under "All").
    """
    rows = conn.execute(
        """
        SELECT enrichments.section AS section, COUNT(*) AS count
        FROM entities
        JOIN scores ON scores.entity_id = entities.id
        JOIN enrichments ON enrichments.entity_id = entities.id
            AND enrichments.computed_at = (
                SELECT MAX(e2.computed_at) FROM enrichments AS e2
                WHERE e2.entity_id = entities.id
            )
        WHERE scores.score_version = :score_version
          AND scores.eligible = 1
          AND enrichments.section IS NOT NULL
          AND scores.run_date = (
              SELECT MAX(latest.run_date)
              FROM scores AS latest
              WHERE latest.score_version = :score_version
          )
        GROUP BY enrichments.section
        """,
        {"score_version": CURRENT_SCORE_VERSION},
    ).fetchall()
    return {row["section"]: row["count"] for row in rows}


def query_partial_history_count(conn: sqlite3.Connection, window_days: int) -> int:
    """Count current-score-version, ineligible entities whose observed
    `window_days` is below the configured window -- these are the entities
    excluded from `query_ranked`'s rows specifically because they are still
    building history (D-08a), not because a full window failed the floor.

    Pinned to the same `MAX(run_date)` as `query_ranked` for the same reason
    -- counting across more than one run_date would double-count an entity
    that (unexpectedly) carries scores rows from two different run_dates.

    Drives the partial-history footer note's singular/plural copy.
    """
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM scores
        WHERE scores.score_version = :score_version
          AND scores.eligible = 0
          AND scores.window_days < :window_days
          AND scores.run_date = (
              SELECT MAX(latest.run_date)
              FROM scores AS latest
              WHERE latest.score_version = :score_version
          )
        """,
        {"score_version": CURRENT_SCORE_VERSION, "window_days": window_days},
    ).fetchone()
    return row["count"]


def query_latest_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Return the most recent successful run_manifest row, or None if the table is empty.

    Any stage counts (DASH-06 planner assumption: "last successful refresh"
    is the newest row whose status is success, for any stage -- not
    specifically the collector stage).
    """
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
