"""Backfill tests (COLL-02, DATA-02, DATA-05, D-05..D-08a).

No test makes a live network call -- stargazer pagination is driven through
an `httpx.MockTransport` (or, for the runner tests, a monkeypatched
`sample_stargazer_history`) per `.claude/CLAUDE.md`'s testing philosophy.

Task 2 covers `techtrend.collectors.backfill` in isolation. Task 3 covers
`techtrend.pipeline.backfill_runner`'s first-sight trigger, provenance-tagged
snapshot writes, and honest per-repo status bookkeeping.
"""

import httpx
import pytest

from techtrend.collectors.backfill import (
    BackfillBlocked,
    BackfillOutcome,
    BackfillTruncated,
    sample_stargazer_history,
)

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
