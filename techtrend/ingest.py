"""Ingest entry point: `python -m techtrend.ingest`.

Default (no-flag) run sequence: setup_logging() -> load_config() ->
connect()+init_db() -> run_collection() over the registered COLLECTORS,
writing entities/snapshots/run_manifest through the source-agnostic pipeline
-> run_backfill() for any first-sight entity -> return 0.

The `--fixture` flag replays a recorded GitHub API response instead of making
a live call, skipping the collection orchestrator/run_manifest -- it remains
the offline development path proven in plan 01-02. Both paths now also
attempt backfill (D-08 triggers on first sight regardless of how an entity
was collected).

Backfill (D-08, D-08a) runs AFTER snapshots are written and inside its own
exception guard: any failure there -- including a missing GITHUB_TOKEN, or
every entity failing -- is caught, recorded as a 'failed' backfill:github
run_manifest row, and never changes this function's exit code or touches
observed snapshots already committed.

Does not write to `scores` (owned by plan 01-04).
"""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from techtrend.db.connection import connect, init_db
from techtrend.logging_setup import setup_logging

logger = logging.getLogger(__name__)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests" / "fixtures" / "github" / "repo_metadata.json"
)


def _load_fixture_sources() -> list[dict]:
    """Read the recorded GitHub repo-metadata fixture as a one-item source list."""
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [raw]


def _upsert_entity(conn, source_record: dict, now: str) -> int:
    """Upsert one entity row keyed on (source, source_native_id). Returns entity id."""
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, homepage,
            discovery_method, admitted_at, last_seen_at
        ) VALUES (
            'github', :native_id, :full_name, :url, :homepage,
            'seed', :now, :now
        )
        ON CONFLICT(source, source_native_id) DO UPDATE SET
            full_name = excluded.full_name,
            url = excluded.url,
            homepage = excluded.homepage,
            last_seen_at = excluded.last_seen_at
        """,
        {
            "native_id": str(source_record["id"]),
            "full_name": source_record["full_name"],
            "url": source_record["html_url"],
            "homepage": source_record.get("homepage"),
            "now": now,
        },
    )
    row = conn.execute(
        "SELECT id FROM entities WHERE source = 'github' AND source_native_id = ?",
        (str(source_record["id"]),),
    ).fetchone()
    return row["id"]


def _upsert_snapshot(conn, entity_id: int, source_record: dict, collected_at: str) -> None:
    """Upsert one 'stars' snapshot row keyed on (entity_id, collected_at, metric_name)."""
    conn.execute(
        """
        INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value, source_kind)
        VALUES (:entity_id, :collected_at, 'stars', :metric_value, 'observed')
        ON CONFLICT(entity_id, collected_at, metric_name) DO UPDATE SET
            metric_value = excluded.metric_value
        """,
        {
            "entity_id": entity_id,
            "collected_at": collected_at,
            "metric_value": source_record["stargazers_count"],
        },
    )


def _attempt_backfill(conn, config, run_date) -> None:
    """Run the D-08 backfill stage after snapshots are committed, inside an
    exception guard that can never propagate. `run_backfill()` already
    catches per-entity failures internally; this guard additionally covers
    catastrophic failures before/around that call -- e.g. a missing
    GITHUB_TOKEN when building the backfill client -- so a run_manifest
    'failed' row is still recorded and the ingest exit code is untouched
    either way (D-08: backfill failure must never block current collection).
    """
    from techtrend.collectors.http import build_client
    from techtrend.pipeline.backfill_runner import run_backfill

    try:
        client = build_client()
        try:
            run_backfill(conn, client, config, run_date)
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 - backfill must never block collection
        logger.warning(
            "stage=backfill:github status=failed error=%s "
            "note=backfill stage skipped this run, observed snapshots unaffected",
            exc,
        )
        from techtrend.pipeline.orchestrator import record_stage

        record_stage(
            conn,
            run_date.isoformat(),
            "backfill:github",
            "failed",
            item_count=0,
            error_detail=str(exc),
        )
        conn.commit()


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    parser = argparse.ArgumentParser(prog="python -m techtrend.ingest")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Replay the recorded GitHub fixture instead of collecting live.",
    )
    args = parser.parse_args(argv)

    from techtrend.config import load_config

    config = load_config()

    conn = connect()
    init_db(conn)

    if args.fixture:
        sources = _load_fixture_sources()
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        collected_at = datetime.now(UTC).strftime("%Y-%m-%d")

        for source_record in sources:
            entity_id = _upsert_entity(conn, source_record, now)
            _upsert_snapshot(conn, entity_id, source_record, collected_at)

        conn.commit()
        logger.info("stage=collect:github items=%d", len(sources))

        run_date = datetime.now(UTC).date()
        _attempt_backfill(conn, config, run_date)
        conn.close()
        return 0

    # Live path: run every registered collector through the source-agnostic
    # pipeline. A collector failure (including a missing auth token) is
    # caught inside run_collection and recorded as a 'failed' run_manifest
    # row with a descriptive error_detail -- never a silent zero-item exit.
    from techtrend.collectors.registry import COLLECTORS
    from techtrend.pipeline.orchestrator import run_collection

    run_date = datetime.now(UTC).date()
    results = run_collection(conn, run_date, COLLECTORS)

    for result in results:
        logger.info(
            "stage=%s status=%s items=%d%s",
            result.stage,
            result.status,
            result.item_count,
            f" error={result.error_detail}" if result.error_detail else "",
        )

    # Ordering backfill after collection means a first-sight entity exists
    # before its history is fetched (D-08).
    _attempt_backfill(conn, config, run_date)
    conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
