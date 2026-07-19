"""Source-agnostic run driver writing run_manifest (HEALTH-01).

`run_collection` iterates the collectors it is passed without ever branching
on `source_id` -- no source name literal may appear anywhere in this module
(COLL-06 structural verification, enforced by an acceptance-criteria grep).
Per-collector failure isolation (Pitfall 1 / T-01-14): one dead source
records `'failed'` and the loop moves on to the next collector rather than
aborting the run.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from techtrend.collectors.base import Collector
from techtrend.pipeline.identity import resolve_entity
from techtrend.pipeline.snapshot import write_snapshot

logger = logging.getLogger(__name__)

_ERROR_DETAIL_MAX_LEN = 500


@dataclass
class StageResult:
    """One collector's outcome for a run -- what `run_collection` returns
    per registered collector, mirroring the row written to `run_manifest`.
    """

    stage: str
    status: str
    item_count: int
    error_detail: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_stage(
    conn,
    run_date: str,
    stage: str,
    status: str,
    item_count: int | None = None,
    error_detail: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    """Upsert on `(run_date, stage)` -- re-running the same stage on the same
    run_date replaces that row rather than appending a second one (HEALTH-01
    ordering). `error_detail` is truncated to 500 characters before storage.
    """
    if error_detail is not None:
        error_detail = error_detail[:_ERROR_DETAIL_MAX_LEN]
    conn.execute(
        """
        INSERT INTO run_manifest (
            run_date, stage, status, item_count, error_detail, started_at, finished_at
        ) VALUES (
            :run_date, :stage, :status, :item_count, :error_detail, :started_at, :finished_at
        )
        ON CONFLICT(run_date, stage) DO UPDATE SET
            status = excluded.status,
            item_count = excluded.item_count,
            error_detail = excluded.error_detail,
            started_at = excluded.started_at,
            finished_at = excluded.finished_at
        """,
        {
            "run_date": run_date,
            "stage": stage,
            "status": status,
            "item_count": item_count,
            "error_detail": error_detail,
            "started_at": started_at or _now_iso(),
            "finished_at": finished_at,
        },
    )


def run_collection(conn, run_date: date, collectors: list[Collector]) -> list[StageResult]:
    """Run every registered collector, resolve each normalized item to an
    entity, write a snapshot per metric, and record one run_manifest row per
    collector -- 'success' (non-zero items), 'zero_items' (ran clean but
    produced nothing -- distinct from 'success' so a silently-dead source is
    never mistaken for a healthy one, Pitfall 1), or 'failed' (raised;
    caught here so one dead collector never aborts the rest of the run).

    Commits once per collector stage so a mid-run crash leaves completed
    stages durable and the next run can simply re-run (DATA-05 -- no
    separate resume-cursor state, per this plan's planner_assumptions).
    """
    run_date_str = run_date.isoformat()
    results: list[StageResult] = []

    for collector in collectors:
        stage = f"collect:{collector.source_id}"
        started_at = _now_iso()
        try:
            raw_items = collector.fetch(run_date)
            for raw in raw_items:
                item = collector.normalize(raw)
                entity_id = resolve_entity(conn, item, datetime.now(UTC))
                if entity_id is None:
                    continue
                for metric_name, metric_value in item.metrics.items():
                    write_snapshot(conn, entity_id, run_date_str, metric_name, metric_value)

            item_count = len(raw_items)
            status = "success" if item_count > 0 else "zero_items"
            finished_at = _now_iso()
            record_stage(
                conn,
                run_date_str,
                stage,
                status,
                item_count=item_count,
                started_at=started_at,
                finished_at=finished_at,
            )
            conn.commit()
            results.append(StageResult(stage=stage, status=status, item_count=item_count))
        except Exception as exc:  # noqa: BLE001 - a dead collector must never abort the run
            finished_at = _now_iso()
            error_detail = str(exc)
            logger.warning(
                "stage=%s status=failed error=%s note=collector skipped, run continues",
                stage,
                error_detail,
            )
            record_stage(
                conn,
                run_date_str,
                stage,
                "failed",
                item_count=0,
                error_detail=error_detail,
                started_at=started_at,
                finished_at=finished_at,
            )
            conn.commit()
            results.append(
                StageResult(stage=stage, status="failed", item_count=0, error_detail=error_detail)
            )

    return results
