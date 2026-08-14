"""Enrich entry point: `python -m techtrend.enrich`.

Sequence: setup_logging() -> load_config() -> connect()+init_db() ->
run_enrichment(...) -> record_stage('enrich', ...) -> commit -> return 0.
Reuses `record_stage` from `techtrend.pipeline.orchestrator` rather than
writing a second run_manifest path -- one writer, one shape, mirroring
`techtrend/score.py`'s precedent exactly.

An enrichment failure records a 'failed' run_manifest row with error detail
and returns a non-zero exit code -- a stale enrichments table after a failed
run must leave a visible trace, never a silent one (D-10/D-16).
"""

import logging
from datetime import UTC, datetime

from techtrend.config import load_config
from techtrend.db.connection import connect, init_db
from techtrend.logging_setup import setup_logging
from techtrend.pipeline.enrich import run_enrichment
from techtrend.pipeline.orchestrator import record_stage

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    config = load_config()
    conn = connect()
    init_db(conn)

    run_date = datetime.now(UTC).date()
    run_date_str = run_date.isoformat()
    started_at = _now_iso()

    try:
        written = run_enrichment(conn, config, run_date)

        status = "success" if written > 0 else "zero_items"
        record_stage(
            conn,
            run_date_str,
            "enrich",
            status,
            item_count=written,
            started_at=started_at,
            finished_at=_now_iso(),
        )
        conn.commit()
        logger.info("stage=enrich status=%s items=%d", status, written)
        return 0
    except Exception as exc:  # noqa: BLE001 - an enrichment failure must never be silent (D-10)
        error_detail = str(exc)
        logger.exception("stage=enrich status=failed error=%s", error_detail)
        record_stage(
            conn,
            run_date_str,
            "enrich",
            "failed",
            item_count=0,
            error_detail=error_detail,
            started_at=started_at,
            finished_at=_now_iso(),
        )
        conn.commit()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
