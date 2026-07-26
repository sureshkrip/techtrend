"""Append-only snapshot upsert (DATA-02, DATA-05).

Keyed on `(entity_id, collected_at, metric_name)` -- day-granularity, one
observation per entity per metric per day (Assumption DATA-02 in the plan's
`<planner_assumptions>`; sub-daily re-runs overwrite rather than append).

`source_kind` defaults to `'observed'` so today's live collection and plan
01-05's backfilled historical points write through this same function --
`'backfill'` vs `'observed'` (D-07) is a parameter, never a parallel write
path.
"""


def write_snapshot(
    conn,
    entity_id: int,
    collected_at: str,
    metric_name: str,
    metric_value: int,
    source_kind: str = "observed",
) -> None:
    """Upsert one snapshot row. Re-running the same-day collection replaces
    `metric_value` rather than appending a duplicate row.

    `source_kind` is updated on conflict too (WR-02 fix), not just
    `metric_value` -- D-07's provenance flag must describe where the
    currently-stored value came from, not where the row originally came
    from. Without this, a later write for the same
    `(entity_id, collected_at, metric_name)` under a different source_kind
    (e.g. a backfill point landing on a day an 'observed' row already
    covers) would overwrite the value but silently keep the stale
    provenance label.
    """
    conn.execute(
        """
        INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value, source_kind)
        VALUES (:entity_id, :collected_at, :metric_name, :metric_value, :source_kind)
        ON CONFLICT(entity_id, collected_at, metric_name) DO UPDATE SET
            metric_value = excluded.metric_value,
            source_kind = excluded.source_kind
        """,
        {
            "entity_id": entity_id,
            "collected_at": collected_at,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "source_kind": source_kind,
        },
    )
