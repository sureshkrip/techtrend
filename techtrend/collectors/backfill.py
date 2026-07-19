"""Sampled stargazer pagination for day-one star history (D-05, D-06, D-08a).

RESEARCH.md's Critical Finding: GitHub restricted the `stargazers` endpoint's
`starred_at` timestamps (the `application/vnd.github.star+json` Accept
header) to a repository's own admins/collaborators as of its 2026-06-30
changelog. For the tracked set this endpoint now returns a permission denial
for nearly every repo. This module still attempts the D-05 mechanism exactly
as specified -- it succeeds for any repo the operator owns or collaborates
on -- and classifies a denial as a distinct, permanent, non-retried outcome
rather than treating it as a transient failure (D-08a graceful degradation).

The auth token env var is never read here -- `techtrend.collectors.http`
owns that (T-01-12); this module only receives an already-built `httpx.Client`.

No third-party star-timeline service is used here (D-05 rejected those
explicitly -- unofficial trackers and public event-warehouse mirrors alike);
Option B is deferred, not adopted here.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx
import tenacity

from techtrend.collectors.http import is_retryable

logger = logging.getLogger(__name__)

GITHUB_API_ROOT = "https://api.github.com"
STARGAZER_ACCEPT_HEADER = "application/vnd.github.star+json"
PAGE_SIZE = 100

# Deliberately faster backoff than github.py's live-collection retry (which
# tunes for real GitHub rate-limit windows) -- this predicate is exercised
# identically (the shared `is_retryable`), only the wait schedule is tightened
# so a unit test covering the transient-retry path does not sleep for tens of
# seconds. The classification boundary this reuses is the load-bearing part,
# not the exact wait timing.
_STARGAZER_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(5),
    "wait": tenacity.wait_exponential(multiplier=0.01, min=0.01, max=0.2),
    "retry": tenacity.retry_if_exception(is_retryable),
}


class BackfillBlocked(Exception):
    """Raised when a stargazer-pagination request hits a permanent
    permission denial (403 without a ratelimit-exhausted header, or 404).

    Raised on the FIRST such response, with no retry -- retrying a platform
    restriction that can never succeed would burn rate-limit quota every run
    (T-01-24). Callers must record this as a distinct 'blocked' state, never
    collapse it into a generic failure or into a false 'complete'.
    """

    def __init__(self, full_name: str, status_code: int):
        self.full_name = full_name
        self.status_code = status_code
        super().__init__(
            f"stargazer history permanently unavailable for {full_name} "
            f"(status {status_code})"
        )


@dataclass
class BackfillOutcome:
    """A successful (possibly partial) sampled star-accrual curve.

    `points` is a list of `(collected_at, cumulative_stars)` pairs, sorted
    ascending by date with no duplicate dates, trimmed to the configured
    lookback window.
    """

    points: list[tuple[str, int]] = field(default_factory=list)
    requests_made: int = 0


@dataclass
class BackfillTruncated(BackfillOutcome):
    """Returned instead of `BackfillOutcome` when the repo has more pages
    than `request_cap` allows resolving -- a coarser curve carrying whatever
    points were gathered within the hard request budget (D-06), never more
    requests than the cap.
    """


def classify_backfill_failure(response: httpx.Response) -> str:
    """Classify a non-2xx stargazer-pagination response as `'permanent'` or
    `'transient'` (T-01-24).

    A 403 WITHOUT `x-ratelimit-remaining: 0`, and any 404, are permanent --
    GitHub's own admin/collaborator restriction on this endpoint
    (RESEARCH.md Critical Finding); retrying can never succeed. A 403 WITH
    that header, and any 5xx, are transient rate-limit/server hiccups and
    flow through the shared `is_retryable` predicate and tenacity backoff.
    """
    if response.status_code == 404:
        return "permanent"
    if response.status_code == 403:
        if response.headers.get("x-ratelimit-remaining") == "0":
            return "transient"
        return "permanent"
    return "transient"


@tenacity.retry(**_STARGAZER_RETRY_KWARGS)
def _fetch_stargazer_page(client: httpx.Client, full_name: str, page: int) -> httpx.Response:
    resp = client.get(
        f"{GITHUB_API_ROOT}/repos/{full_name}/stargazers",
        params={"page": page, "per_page": PAGE_SIZE},
        headers={"Accept": STARGAZER_ACCEPT_HEADER},
    )
    if resp.status_code >= 400:
        if classify_backfill_failure(resp) == "permanent":
            # Raised directly (not via raise_for_status()) so `is_retryable`
            # -- which only recognizes httpx.HTTPStatusError -- never sees
            # this, and tenacity gives up on the first attempt.
            raise BackfillBlocked(full_name, resp.status_code)
        resp.raise_for_status()
    return resp


def _select_page_indices(last_page: int, request_cap: int) -> tuple[list[int], bool]:
    """Return (descending 1-based page indices to fetch, truncated flag).

    Never returns more than `request_cap` indices. When the repo's total
    page count fits within the cap, every page is fetched (untruncated).
    When it doesn't, a fixed-stride reverse sample of exactly `request_cap`
    pages is walked from the newest page backwards -- the repo is too large
    to resolve within budget, so the curve is coarser rather than the
    request count exceeding the cap (D-06).
    """
    if last_page <= request_cap:
        return list(range(last_page, 0, -1)), False

    stride = last_page / request_cap
    indices: list[int] = []
    seen: set[int] = set()
    for i in range(request_cap):
        idx = last_page - round(i * stride)
        idx = max(1, min(last_page, idx))
        while idx in seen and idx > 1:
            idx -= 1
        seen.add(idx)
        indices.append(idx)
    return indices, True


def _dedupe_and_sort(points: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Collapse same-date points (keeping the larger cumulative count -- the
    later observation for that date) and return ascending by date.
    """
    by_date: dict[str, int] = {}
    for collected_at, cumulative in points:
        if collected_at not in by_date or cumulative > by_date[collected_at]:
            by_date[collected_at] = cumulative
    return sorted(by_date.items())


def _trim_to_lookback(
    points: list[tuple[str, int]], lookback_days: int
) -> list[tuple[str, int]]:
    """Keep only points within `lookback_days` of the newest sampled point --
    anchored to the data itself so the trim is deterministic regardless of
    when the run happens to execute.
    """
    if not points:
        return points
    newest = date.fromisoformat(points[-1][0])
    cutoff = newest - timedelta(days=lookback_days)
    return [(d, v) for d, v in points if date.fromisoformat(d) >= cutoff]


def sample_stargazer_history(
    client: httpx.Client,
    full_name: str,
    stars_total: int,
    request_cap: int,
    lookback_days: int,
) -> BackfillOutcome:
    """Reconstruct a bounded `(date, cumulative_stars)` curve via fixed-stride
    reverse-sampled stargazer pagination (D-05, D-06).

    Walks pages backwards from the newest, staying at or below `request_cap`
    requests. Each sampled page's first entry's `starred_at` is paired with
    the cumulative star count implied by that page's ordinal position,
    producing a monotonic curve without ever walking every page. Raises
    `BackfillBlocked` immediately (no retry) on a permanent permission
    denial; returns a `BackfillTruncated` when the repo's total page count
    exceeds the cap.
    """
    if stars_total <= 0:
        return BackfillOutcome(points=[], requests_made=0)

    last_page = math.ceil(stars_total / PAGE_SIZE)
    page_indices, truncated = _select_page_indices(last_page, request_cap)

    points: list[tuple[str, int]] = []
    requests_made = 0
    for page in page_indices:
        resp = _fetch_stargazer_page(client, full_name, page)
        requests_made += 1
        entries = resp.json()
        if not entries:
            continue
        starred_at = entries[0]["starred_at"]
        collected_at = starred_at[:10]
        cumulative_stars = min(page * PAGE_SIZE, stars_total)
        points.append((collected_at, cumulative_stars))

    points = _dedupe_and_sort(points)
    points = _trim_to_lookback(points, lookback_days)

    outcome_cls = BackfillTruncated if truncated else BackfillOutcome
    return outcome_cls(points=points, requests_made=requests_made)
