"""Backfill tests (COLL-02, DATA-02, DATA-05, D-05..D-08a).

No test makes a live network call -- stargazer pagination is driven through
an `httpx.MockTransport` (or, for the runner tests, a monkeypatched
`sample_stargazer_history`) per `.claude/CLAUDE.md`'s testing philosophy.

Task 2 covers `techtrend.collectors.backfill` in isolation. Task 3 covers
`techtrend.pipeline.backfill_runner`'s first-sight trigger, provenance-tagged
snapshot writes, and honest per-repo status bookkeeping.
"""

from datetime import date

import httpx
import pytest

import techtrend.pipeline.backfill_runner as backfill_runner
from techtrend.collectors.backfill import (
    BackfillBlocked,
    BackfillOutcome,
    BackfillTruncated,
    sample_stargazer_history,
)
from techtrend.config import load_config
from techtrend.pipeline.backfill_runner import run_backfill
from techtrend.pipeline.snapshot import write_snapshot

# ---------------------------------------------------------------------------
# Task 2: techtrend.collectors.backfill
# ---------------------------------------------------------------------------


def test_403_marks_blocked_not_retried(github_fixture):
    body = github_fixture("stargazers_403.json")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(403, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(BackfillBlocked):
            sample_stargazer_history(
                client, "octo/repo", stars_total=500, request_cap=20, lookback_days=90
            )
    finally:
        client.close()

    assert len(calls) == 1


def test_404_marks_blocked_same_as_403(github_fixture):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404, json={"message": "Not Found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(BackfillBlocked):
            sample_stargazer_history(
                client, "octo/gone", stars_total=500, request_cap=20, lookback_days=90
            )
    finally:
        client.close()

    assert len(calls) == 1


def test_403_with_ratelimit_remaining_zero_is_retried_then_succeeds(github_fixture):
    body_403 = github_fixture("stargazers_403.json")
    page = github_fixture("stargazers_page.json")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(403, json=body_403, headers={"x-ratelimit-remaining": "0"})
        return httpx.Response(200, json=page)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        outcome = sample_stargazer_history(
            client, "octo/repo", stars_total=50, request_cap=20, lookback_days=90
        )
    finally:
        client.close()

    assert isinstance(outcome, BackfillOutcome)
    assert not isinstance(outcome, BackfillTruncated)
    # One transient 403 (retried, not raised) then one successful page fetch.
    assert len(calls) == 2
    assert len(outcome.points) == 1


def test_successful_pagination_returns_ascending_sorted_unique_dates(github_fixture):
    base_entry = github_fixture("stargazers_page.json")[0]
    calls: list[httpx.Request] = []
    dates_by_page = {1: "2026-04-01", 2: "2026-05-15", 3: "2026-07-10"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        page = int(dict(request.url.params).get("page", "1"))
        entry = {**base_entry, "starred_at": f"{dates_by_page[page]}T00:00:00Z"}
        return httpx.Response(200, json=[entry])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        outcome = sample_stargazer_history(
            client, "octo/repo", stars_total=250, request_cap=20, lookback_days=365
        )
    finally:
        client.close()

    assert isinstance(outcome, BackfillOutcome)
    assert not isinstance(outcome, BackfillTruncated)
    assert len(calls) == 3  # last_page = ceil(250/100) = 3, all fetched (untruncated)
    result_dates = [d for d, _ in outcome.points]
    assert result_dates == sorted(result_dates)
    assert len(result_dates) == len(set(result_dates))


def test_pagination_capped_and_returns_truncated_outcome(github_fixture):
    base_entry = github_fixture("stargazers_page.json")[0]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        entry = {**base_entry, "starred_at": "2026-06-01T00:00:00Z"}
        return httpx.Response(200, json=[entry])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        # stars_total=5,000,000 -> last_page = 50,000, far exceeding the cap.
        outcome = sample_stargazer_history(
            client, "octo/huge-repo", stars_total=5_000_000, request_cap=5, lookback_days=90
        )
    finally:
        client.close()

    assert isinstance(outcome, BackfillTruncated)
    assert len(calls) == 5  # never exceeds request_cap
    assert outcome.requests_made == 5


def test_points_trimmed_to_lookback_days(github_fixture):
    base_entry = github_fixture("stargazers_page.json")[0]
    dates_by_page = {1: "2025-01-01", 2: "2026-06-01"}

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(dict(request.url.params).get("page", "1"))
        entry = {**base_entry, "starred_at": f"{dates_by_page[page]}T00:00:00Z"}
        return httpx.Response(200, json=[entry])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        # stars_total=150 -> last_page = 2, untruncated (2 <= 20).
        outcome = sample_stargazer_history(
            client, "octo/repo", stars_total=150, request_cap=20, lookback_days=90
        )
    finally:
        client.close()

    result_dates = [d for d, _ in outcome.points]
    assert "2025-01-01" not in result_dates
    assert "2026-06-01" in result_dates


# ---------------------------------------------------------------------------
# Task 3: techtrend.pipeline.backfill_runner
# ---------------------------------------------------------------------------


def _insert_entity(conn, native_id: str, full_name: str, backfill_status: str) -> int:
    now = "2026-07-19T00:00:00Z"
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, discovery_method,
            admitted_at, last_seen_at, backfill_status
        ) VALUES ('github', :native_id, :full_name, :url, 'seed', :now, :now, :status)
        """,
        {
            "native_id": native_id,
            "full_name": full_name,
            "url": f"https://github.com/{full_name}",
            "now": now,
            "status": backfill_status,
        },
    )
    row = conn.execute(
        "SELECT id FROM entities WHERE source = 'github' AND source_native_id = ?",
        (native_id,),
    ).fetchone()
    conn.commit()
    return row["id"]


@pytest.fixture
def config():
    return load_config()


def test_pending_entity_attempted_complete_and_blocked_entities_skipped(db, config, monkeypatch):
    conn = db
    pending_id = _insert_entity(conn, "1", "octo/pending-repo", "pending")
    complete_id = _insert_entity(conn, "2", "octo/complete-repo", "complete")
    blocked_id = _insert_entity(conn, "3", "octo/blocked-repo", "blocked")
    for entity_id in (pending_id, complete_id, blocked_id):
        write_snapshot(conn, entity_id, "2026-07-19", "stars", 500, source_kind="observed")
    conn.commit()

    attempted: list[str] = []

    def fake_sample(client, full_name, stars_total, request_cap, lookback_days):
        attempted.append(full_name)
        return BackfillOutcome(points=[("2026-07-01", 100)], requests_made=1)

    monkeypatch.setattr(backfill_runner, "sample_stargazer_history", fake_sample)

    run_backfill(conn, object(), config, date(2026, 7, 19))

    assert attempted == ["octo/pending-repo"]


def test_failed_and_truncated_entities_are_retried(db, config, monkeypatch):
    conn = db
    failed_id = _insert_entity(conn, "1", "octo/failed-repo", "failed")
    truncated_id = _insert_entity(conn, "2", "octo/truncated-repo", "truncated")
    for entity_id in (failed_id, truncated_id):
        write_snapshot(conn, entity_id, "2026-07-19", "stars", 500, source_kind="observed")
    conn.commit()

    attempted: list[str] = []

    def fake_sample(client, full_name, stars_total, request_cap, lookback_days):
        attempted.append(full_name)
        return BackfillOutcome(points=[("2026-07-01", 100)], requests_made=1)

    monkeypatch.setattr(backfill_runner, "sample_stargazer_history", fake_sample)

    run_backfill(conn, object(), config, date(2026, 7, 19))

    assert set(attempted) == {"octo/failed-repo", "octo/truncated-repo"}


def test_successful_backfill_writes_backfill_snapshots_and_status_complete(
    db, config, monkeypatch
):
    conn = db
    entity_id = _insert_entity(conn, "1", "octo/repo", "pending")
    write_snapshot(conn, entity_id, "2026-07-19", "stars", 500, source_kind="observed")
    conn.commit()

    def fake_sample(client, full_name, stars_total, request_cap, lookback_days):
        return BackfillOutcome(
            points=[("2026-04-01", 100), ("2026-06-01", 300)], requests_made=2
        )

    monkeypatch.setattr(backfill_runner, "sample_stargazer_history", fake_sample)

    run_backfill(conn, object(), config, date(2026, 7, 19))

    rows = conn.execute(
        "SELECT collected_at, metric_value, source_kind FROM snapshots "
        "WHERE entity_id = ? AND source_kind = 'backfill' ORDER BY collected_at",
        (entity_id,),
    ).fetchall()
    assert [dict(r) for r in rows] == [
        {"collected_at": "2026-04-01", "metric_value": 100, "source_kind": "backfill"},
        {"collected_at": "2026-06-01", "metric_value": 300, "source_kind": "backfill"},
    ]

    entity = conn.execute(
        "SELECT backfill_status, backfilled_at FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()
    assert entity["backfill_status"] == "complete"
    assert entity["backfilled_at"] is not None


def test_rerunning_backfill_does_not_duplicate_snapshot_rows(db, config, monkeypatch):
    conn = db
    entity_id = _insert_entity(conn, "1", "octo/repo", "pending")
    write_snapshot(conn, entity_id, "2026-07-19", "stars", 500, source_kind="observed")
    conn.commit()

    def fake_sample(client, full_name, stars_total, request_cap, lookback_days):
        return BackfillOutcome(points=[("2026-04-01", 100)], requests_made=1)

    monkeypatch.setattr(backfill_runner, "sample_stargazer_history", fake_sample)

    run_backfill(conn, object(), config, date(2026, 7, 19))
    count_after_first = conn.execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()["n"]

    # D-08 only retries 'failed'/'truncated', not 'complete' -- reset the
    # status to genuinely re-exercise write_snapshot()'s upsert idempotency
    # with the same derived points, rather than trivially no-op-ing because
    # the entity is skipped.
    conn.execute("UPDATE entities SET backfill_status = 'pending' WHERE id = ?", (entity_id,))
    conn.commit()

    run_backfill(conn, object(), config, date(2026, 7, 19))
    count_after_second = conn.execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()["n"]

    assert count_after_second == count_after_first


def test_blocked_outcome_sets_status_blocked_and_writes_zero_snapshots(db, config, monkeypatch):
    conn = db
    entity_id = _insert_entity(conn, "1", "octo/repo", "pending")
    write_snapshot(conn, entity_id, "2026-07-19", "stars", 500, source_kind="observed")
    conn.commit()

    def fake_sample(client, full_name, stars_total, request_cap, lookback_days):
        raise BackfillBlocked(full_name, 403)

    monkeypatch.setattr(backfill_runner, "sample_stargazer_history", fake_sample)

    run_backfill(conn, object(), config, date(2026, 7, 19))

    entity = conn.execute(
        "SELECT backfill_status FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()
    assert entity["backfill_status"] == "blocked"

    n = conn.execute(
        "SELECT COUNT(*) AS n FROM snapshots WHERE entity_id = ? AND source_kind = 'backfill'",
        (entity_id,),
    ).fetchone()["n"]
    assert n == 0


def test_backfill_raising_for_every_entity_does_not_abort_or_lose_observed_snapshots(
    db, config, monkeypatch
):
    conn = db
    entity_a = _insert_entity(conn, "1", "octo/repo-a", "pending")
    entity_b = _insert_entity(conn, "2", "octo/repo-b", "pending")
    write_snapshot(conn, entity_a, "2026-07-19", "stars", 500, source_kind="observed")
    write_snapshot(conn, entity_b, "2026-07-19", "stars", 700, source_kind="observed")
    conn.commit()

    observed_before = conn.execute(
        "SELECT COUNT(*) AS n FROM snapshots WHERE source_kind = 'observed'"
    ).fetchone()["n"]

    def fake_sample(client, full_name, stars_total, request_cap, lookback_days):
        raise RuntimeError("boom")

    monkeypatch.setattr(backfill_runner, "sample_stargazer_history", fake_sample)

    # Must not raise.
    counts = run_backfill(conn, object(), config, date(2026, 7, 19))

    observed_after = conn.execute(
        "SELECT COUNT(*) AS n FROM snapshots WHERE source_kind = 'observed'"
    ).fetchone()["n"]
    assert observed_after == observed_before
    assert counts["failed"] == 2
    assert counts["completed"] == 0


def test_run_manifest_row_records_completed_blocked_failed_counts(db, config, monkeypatch):
    conn = db
    complete_id = _insert_entity(conn, "1", "octo/complete-repo", "pending")
    blocked_id = _insert_entity(conn, "2", "octo/blocked-repo", "pending")
    write_snapshot(conn, complete_id, "2026-07-19", "stars", 500, source_kind="observed")
    write_snapshot(conn, blocked_id, "2026-07-19", "stars", 500, source_kind="observed")
    conn.commit()

    def fake_sample(client, full_name, stars_total, request_cap, lookback_days):
        if full_name == "octo/blocked-repo":
            raise BackfillBlocked(full_name, 403)
        return BackfillOutcome(points=[("2026-06-01", 10)], requests_made=1)

    monkeypatch.setattr(backfill_runner, "sample_stargazer_history", fake_sample)

    run_backfill(conn, object(), config, date(2026, 7, 19))

    row = conn.execute(
        "SELECT item_count, error_detail, status FROM run_manifest "
        "WHERE run_date = ? AND stage = 'backfill:github'",
        ("2026-07-19",),
    ).fetchone()
    assert row is not None
    assert row["item_count"] == 1  # one completed
    assert "blocked=1" in row["error_detail"]
    assert "failed=0" in row["error_detail"]
