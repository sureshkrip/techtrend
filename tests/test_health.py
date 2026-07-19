"""Run health tests (HEALTH-01): per-source outcome recording distinguishes
success from silence (zero items) from failure, and one run_manifest row
exists per registered collector every run -- Pitfall 1's mitigation.

HEALTH-01's basic upsert-idempotency guarantee is proven in test_storage.py;
this file covers orchestrator-level failure isolation and the
success/zero_items/failed distinction.
"""

from datetime import date

from techtrend.collectors.base import CollectedItem
from techtrend.pipeline.orchestrator import record_stage, run_collection


class _FakeCollector:
    """Minimal `Collector` for orchestrator tests -- no live network call."""

    def __init__(self, source_id, raw_items=None, normalize_fn=None, fetch_error=None):
        self.source_id = source_id
        self._raw_items = raw_items or []
        self._normalize_fn = normalize_fn or (lambda raw: raw)
        self._fetch_error = fetch_error

    def fetch(self, since):  # noqa: ARG002 - since unused by the fake
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._raw_items

    def normalize(self, raw):
        return self._normalize_fn(raw)


def _dummy_item(native_id: str) -> CollectedItem:
    return CollectedItem(
        source="dummy",
        source_native_id=native_id,
        full_name=f"dummy/{native_id}",
        url=f"https://example.com/{native_id}",
        metrics={"stars": 1},
        discovery_method="seed",
    )


def test_failing_collector_records_failed_status_and_does_not_abort_run(db):
    failing = _FakeCollector("broken", fetch_error=RuntimeError("upstream exploded"))
    healthy = _FakeCollector(
        "healthy", raw_items=[{"id": "1"}], normalize_fn=lambda raw: _dummy_item(raw["id"])
    )

    results = run_collection(db, date(2026, 7, 19), [failing, healthy])

    failed_result = next(r for r in results if r.stage == "collect:broken")
    healthy_result = next(r for r in results if r.stage == "collect:healthy")

    assert failed_result.status == "failed"
    assert failed_result.error_detail is not None
    assert "upstream exploded" in failed_result.error_detail
    assert healthy_result.status == "success"
    assert healthy_result.item_count == 1

    manifest_rows = {
        r["stage"]: r["status"]
        for r in db.execute("SELECT stage, status FROM run_manifest")
    }
    assert manifest_rows["collect:broken"] == "failed"
    assert manifest_rows["collect:healthy"] == "success"


def test_zero_items_flagged_not_silent(db):
    """A stage that succeeds but returns zero items records 'zero_items',
    distinct from both 'success' and 'failed' (HEALTH-01 adjacency).
    """
    quiet = _FakeCollector("quiet", raw_items=[])

    run_collection(db, date(2026, 7, 19), [quiet])

    row = db.execute(
        "SELECT status FROM run_manifest WHERE stage = 'collect:quiet'"
    ).fetchone()
    assert row["status"] == "zero_items"
    assert row["status"] not in ("success", "failed")


def test_no_collector_produces_items_still_writes_one_row_per_collector(db):
    a = _FakeCollector("source-a", raw_items=[])
    b = _FakeCollector("source-b", raw_items=[])

    run_collection(db, date(2026, 7, 19), [a, b])

    rows = db.execute("SELECT stage FROM run_manifest").fetchall()
    stages = {r["stage"] for r in rows}
    assert stages == {"collect:source-a", "collect:source-b"}
    assert len(rows) == 2


def test_record_stage_same_run_date_and_stage_replaces_not_appends(db):
    record_stage(db, "2026-07-19", "collect:github", "success", item_count=10)
    record_stage(db, "2026-07-19", "collect:github", "failed", item_count=0, error_detail="boom")
    db.commit()

    rows = db.execute(
        "SELECT status, item_count, error_detail FROM run_manifest"
        " WHERE run_date = '2026-07-19' AND stage = 'collect:github'"
    ).fetchall()

    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["item_count"] == 0
    assert rows[0]["error_detail"] == "boom"
