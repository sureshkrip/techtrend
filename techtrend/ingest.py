"""Ingest entry point: `python -m techtrend.ingest`.

Run sequence: setup_logging() -> load_config() -> connect()+init_db() -> per
source, upsert entities then snapshots -> commit once -> return 0.

The `--fixture` flag replays a recorded GitHub API response instead of making
a live call. Live collection is deliberately NOT implemented here -- plan
01-03 replaces the fixture branch with the real collector. The fixture branch
remains afterwards as the offline development path.

Does not write to `scores` (owned by plan 01-04) or `run_manifest` (owned by
plan 01-03) -- the dashboard must tolerate both being empty.
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

    load_config()

    if args.fixture:
        sources = _load_fixture_sources()
    else:
        logger.info(
            "stage=collect:github items=0 note=live collection not implemented in this plan"
        )
        sources = []

    conn = connect()
    init_db(conn)

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    collected_at = datetime.now(UTC).strftime("%Y-%m-%d")

    for source_record in sources:
        entity_id = _upsert_entity(conn, source_record, now)
        _upsert_snapshot(conn, entity_id, source_record, collected_at)

    conn.commit()
    conn.close()

    logger.info("stage=collect:github items=%d", len(sources))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
