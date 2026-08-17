"""Run health tests (HEALTH-01, HEALTH-02, D-16): per-source outcome
recording distinguishes success from silence (zero items) from failure, one
run_manifest row exists per registered collector every run (Pitfall 1's
mitigation), and the dashboard's escalating health strip renders the
correct tier and Copywriting Contract string for every D-16 escalation
case.

HEALTH-01's basic upsert-idempotency guarantee is proven in test_storage.py;
this file covers orchestrator-level failure isolation, the
success/zero_items/failed distinction, and (below) `health_status()`'s
three-tier escalation logic plus its rendering into the dashboard.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from techtrend.collectors.base import CollectedItem
from techtrend.config import Config
from techtrend.pipeline.orchestrator import record_stage, run_collection
from techtrend.server.health import HealthTier, health_status


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


# --- health_status() three-tier escalation (D-16, HEALTH-02) ---


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_recent_success_yields_normal_tier_with_relative_time(db, frozen_now):
    finished = frozen_now - timedelta(hours=2)
    record_stage(
        db,
        "2026-07-19",
        "collect:github",
        "success",
        item_count=10,
        started_at=_iso(finished),
        finished_at=_iso(finished),
    )
    db.commit()

    result = health_status(db, Config(), frozen_now)

    assert result["tier"] == HealthTier.normal
    assert "2 hours ago" in result["message"]


def test_stale_run_yields_stale_tier_and_copy(db, frozen_now):
    finished = frozen_now - timedelta(hours=40)
    record_stage(
        db,
        "2026-07-17",
        "collect:github",
        "success",
        item_count=10,
        started_at=_iso(finished),
        finished_at=_iso(finished),
    )
    db.commit()

    result = health_status(db, Config(), frozen_now)

    assert result["tier"] == HealthTier.stale
    assert "Data may be out of date" in result["message"]
    # relative_time() switches to day-granularity at 24h -- 40 hours ago
    # renders as "1 day ago", not "40 hours ago".
    assert "1 day ago" in result["message"]
    assert "ago ago" not in result["message"]


def test_staleness_boundary_is_inclusive_on_the_healthy_side(db, frozen_now):
    exactly_threshold = frozen_now - timedelta(hours=36)
    record_stage(
        db,
        "2026-07-18",
        "collect:github",
        "success",
        item_count=10,
        started_at=_iso(exactly_threshold),
        finished_at=_iso(exactly_threshold),
    )
    db.commit()

    assert health_status(db, Config(), frozen_now)["tier"] == HealthTier.normal


def test_staleness_boundary_one_minute_past_is_stale(db, frozen_now):
    past_threshold = frozen_now - timedelta(hours=36, minutes=1)
    record_stage(
        db,
        "2026-07-18",
        "collect:github",
        "success",
        item_count=10,
        started_at=_iso(past_threshold),
        finished_at=_iso(past_threshold),
    )
    db.commit()

    assert health_status(db, Config(), frozen_now)["tier"] == HealthTier.stale


def test_failed_collector_yields_critical_with_failure_copy(db, frozen_now):
    good = frozen_now - timedelta(hours=5)
    record_stage(
        db,
        "2026-07-18",
        "collect:github",
        "success",
        item_count=10,
        started_at=_iso(good),
        finished_at=_iso(good),
    )
    bad = frozen_now - timedelta(hours=1)
    record_stage(
        db,
        "2026-07-19",
        "collect:github",
        "failed",
        item_count=0,
        error_detail="upstream exploded",
        started_at=_iso(bad),
        finished_at=_iso(bad),
    )
    db.commit()

    result = health_status(db, Config(), frozen_now)

    assert result["tier"] == HealthTier.critical
    assert "collection failed" in result["message"].lower()
    assert "5 hours ago" in result["message"]
    assert "ago ago" not in result["message"]


def test_failed_score_stage_escalates_health_even_though_collect_succeeded(db, frozen_now):
    """WR-01: a healthy `collect:github` stage must not mask a failed `score`
    stage -- the health strip is the only user-visible trace of a scoring
    failure per score.py's own docstring ("a stale scores table after a
    failed run must leave a visible trace, never a silent one", T-01-20).
    """
    good = frozen_now - timedelta(hours=1)
    record_stage(
        db,
        "2026-07-19",
        "collect:github",
        "success",
        item_count=10,
        started_at=_iso(good),
        finished_at=_iso(good),
    )
    record_stage(
        db,
        "2026-07-19",
        "score",
        "failed",
        item_count=0,
        error_detail="unexpected data shape",
        started_at=_iso(good),
        finished_at=_iso(good),
    )
    db.commit()

    result = health_status(db, Config(), frozen_now)

    assert result["tier"] == HealthTier.critical
    assert result["tier"] != HealthTier.normal


def test_never_completed_uses_distinct_copy(db, frozen_now):
    """An empty run_manifest (no collector run has ever succeeded) takes
    the distinct 'never completed successfully' copy, not the 'failed on
    the last run' copy -- a brand-new install must read as still gathering
    data, not as a defect (D-08a).
    """
    result = health_status(db, Config(), frozen_now)

    assert result["tier"] == HealthTier.critical
    assert "never completed successfully" in result["message"]
    assert "failed on the last run" not in result["message"]


def test_zero_items_against_non_trivial_trailing_average_is_critical(db, frozen_now):
    for i, run_date in enumerate(["2026-07-15", "2026-07-16", "2026-07-17", "2026-07-18"]):
        finished = frozen_now - timedelta(hours=10 + (4 - i) * 24)
        record_stage(
            db,
            run_date,
            "collect:github",
            "success",
            item_count=20,
            started_at=_iso(finished),
            finished_at=_iso(finished),
        )
    recent = frozen_now - timedelta(hours=1)
    record_stage(
        db,
        "2026-07-19",
        "collect:github",
        "zero_items",
        item_count=0,
        started_at=_iso(recent),
        finished_at=_iso(recent),
    )
    db.commit()

    result = health_status(db, Config(), frozen_now)

    assert result["tier"] == HealthTier.critical


def test_zero_items_against_trailing_average_of_zero_is_not_critical(db, frozen_now):
    """A prior successful run exists (so the distinct 'never completed'
    branch does not fire first), but with item_count=0 -- an edge
    combination constructed directly to exercise the trailing-average
    floor check in isolation. A genuine brand-new install (empty
    run_manifest) hits 'never completed successfully' instead, covered by
    test_never_completed_uses_distinct_copy.
    """
    older_good = frozen_now - timedelta(hours=50)
    record_stage(
        db,
        "2026-07-17",
        "collect:github",
        "success",
        item_count=0,
        started_at=_iso(older_good),
        finished_at=_iso(older_good),
    )
    recent = frozen_now - timedelta(hours=2)
    record_stage(
        db,
        "2026-07-19",
        "collect:github",
        "zero_items",
        item_count=0,
        started_at=_iso(recent),
        finished_at=_iso(recent),
    )
    db.commit()

    result = health_status(db, Config(), frozen_now)

    assert result["tier"] != HealthTier.critical


# --- Rendered health strip (integration, via the dashboard route) ---


def _client_for(pg_env):
    """Depends on the `pg_env` fixture already having pointed
    techtrend.db.connection.connect()'s zero-arg PG* env-var path at the
    ephemeral test database -- callers must also request `pg_env`.
    """
    from techtrend.server.app import app

    return TestClient(app)


def test_error_detail_truncated_in_rendered_health_strip(db, pg_env):
    now = datetime.now(UTC)
    good = now - timedelta(hours=1)
    record_stage(
        db,
        "2026-07-18",
        "collect:github",
        "success",
        item_count=10,
        started_at=_iso(good),
        finished_at=_iso(good),
    )
    long_detail = "E" * 200
    record_stage(
        db,
        "2026-07-19",
        "collect:github",
        "failed",
        item_count=0,
        error_detail=long_detail,
        started_at=_iso(good),
        finished_at=_iso(good),
    )
    db.commit()

    response = _client_for(pg_env).get("/")

    assert response.status_code == 200
    truncated = ("E" * 120) + "..."
    assert truncated in response.text
    assert long_detail not in response.text


def test_health_strip_renders_for_normal_tier(db, pg_env):
    now = datetime.now(UTC)
    recent = now - timedelta(hours=1)
    record_stage(
        db,
        "2026-07-19",
        "collect:github",
        "success",
        item_count=5,
        started_at=_iso(recent),
        finished_at=_iso(recent),
    )
    db.commit()

    response = _client_for(pg_env).get("/")

    assert response.status_code == 200
    assert "health-strip" in response.text
    assert "health-normal" in response.text


def test_health_strip_renders_for_critical_tier_on_empty_run_manifest(db, pg_env):
    """The health strip is persistent -- present unconditionally, including
    in the critical tier on a totally empty run_manifest (a brand-new
    install), not only in the normal case.
    """
    response = _client_for(pg_env).get("/")

    assert response.status_code == 200
    assert "health-strip" in response.text
    assert "health-critical" in response.text
    assert "never completed successfully" in response.text
