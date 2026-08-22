---
phase: 03-source-breadth-discourse-downloads-changelogs
plan: 04
subsystem: collectors
tags: [httpx, tenacity, pydantic, algolia, hacker-news]

requires:
  - phase: 03-source-breadth-discourse-downloads-changelogs
    provides: "03-02: build_public_client/is_retryable_public (http.py), HackerNews config model (config.py)"
  - phase: 03-source-breadth-discourse-downloads-changelogs
    provides: "03-01: normalize.PRIMARY_METRIC['hn'] = 'points'"
provides:
  - HNCollector implementing the Collector protocol over the Algolia HN Search API
  - Fixture-backed, network-free test suite for the HN collector
affects: [03-06 (registry wiring for HN/npm/PyPI/changelog collectors)]

tech-stack:
  added: []
  patterns:
    - "Per-keyword search-pass isolation (log + skip on HTTPStatusError/TransportError, mirroring GitHubCollector._discover)"
    - "Self-post URL fallback to the source's own permalink when no external url exists"

key-files:
  created:
    - techtrend/collectors/hn.py
    - tests/test_collect_hn.py
    - tests/fixtures/hn/search_response.json
  modified: []

key-decisions:
  - "Used the Algolia search_by_date endpoint (not the relevance-ranked search endpoint) so numericFilters on created_at_i correctly scopes results to the configured lookback window"

patterns-established:
  - "Wave 2 collector modules stay registry-free by design -- registry.py wiring is deferred to the Wave 3 integration plan (03-06) to keep parallel collector plans conflict-free"

requirements-completed: [COLL-03]

coverage:
  - id: D1
    description: "HNCollector.fetch() queries the Algolia HN Search API once per configured keyword, dedupes hits by objectID, and isolates per-keyword search failures without aborting the run"
    requirement: "COLL-03"
    verification:
      - kind: unit
        ref: "tests/test_collect_hn.py#test_fetch_issues_one_request_per_keyword_and_dedupes_by_object_id"
        status: pass
      - kind: unit
        ref: "tests/test_collect_hn.py#test_fetch_transport_error_skips_pass_not_whole_run"
        status: pass
      - kind: unit
        ref: "tests/test_collect_hn.py#test_fetch_with_no_keywords_issues_no_requests"
        status: pass
    human_judgment: false
  - id: D2
    description: "HNCollector.normalize() maps a raw Algolia hit onto CollectedItem with metrics={'points': N}, falling back to the HN item permalink when url is null"
    requirement: "COLL-03"
    verification:
      - kind: unit
        ref: "tests/test_collect_hn.py#test_normalize_maps_points_into_metrics"
        status: pass
      - kind: unit
        ref: "tests/test_collect_hn.py#test_normalize_null_url_falls_back_to_hn_permalink"
        status: pass
      - kind: unit
        ref: "tests/test_collect_hn.py#test_normalize_missing_points_defaults_to_zero"
        status: pass
    human_judgment: false
  - id: D3
    description: "HNCollector satisfies the Collector protocol with source_id == 'hn'"
    requirement: "COLL-03"
    verification:
      - kind: unit
        ref: "tests/test_collect_hn.py#test_hn_collector_satisfies_collector_protocol"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-08-22
status: complete
---

# Phase 3 Plan 4: Hacker News Collector Summary

**HNCollector queries the Algolia HN Search API (search_by_date) per configured keyword, dedupes by objectID, and normalizes stories into CollectedItem(metrics={"points": N}) with a permalink fallback for self-posts -- fully fixture-backed, no live network in tests.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-08-22T18:20:00-04:00 (approx)
- **Completed:** 2026-08-22T18:24:31-04:00
- **Tasks:** 3
- **Files modified:** 3 (all new)

## Accomplishments
- Recorded a representative Algolia HN Search fixture with 3 hits, including two self-posts (`url: null`) to exercise the permalink fallback
- Implemented `HNCollector` (`techtrend/collectors/hn.py`) mirroring `GitHubCollector`'s shape: lazy config/client resolution, per-keyword search with `numericFilters` on `created_at_i`, dedupe-by-objectID, per-keyword failure isolation, and `normalize()` mapping to `metrics={"points": N}`
- Wrote a fixture-backed, network-free test suite (7 tests) covering fetch dedupe/one-request-per-keyword, transport-error pass isolation, empty-keyword-list no-op, normalize points mapping, null-url permalink fallback, missing-points defaulting to 0, and `Collector` protocol conformance

## Task Commits

Each task was committed atomically:

1. **Task 1: Record the HN Algolia fixture** - `62a1093` (test)
2. **Task 2: Implement HNCollector** - `ccb48dd` (feat)
3. **Task 3: HN collector tests (fixture-backed, no network)** - `2494bb9` (test)

**Plan metadata:** (this commit — docs, not staged with SUMMARY.md/STATE.md/ROADMAP.md per plan constraints)

## Files Created/Modified
- `techtrend/collectors/hn.py` - `HNCollector` implementing `Collector` (`source_id = "hn"`), Algolia `search_by_date` client, per-keyword dedupe, self-post permalink fallback
- `tests/test_collect_hn.py` - 7 fixture-backed tests, no live network
- `tests/fixtures/hn/search_response.json` - recorded 3-hit Algolia response with two `url: null` self-posts

## Decisions Made
- Used `search_by_date` (not the relevance-ranked `search` endpoint) since `numericFilters=created_at_i>{cutoff}` needs a recency-scoped query shape — confirmed live in 03-RESEARCH.md.
- `since: date` parameter is accepted (protocol conformance) but not used to scope the query beyond `config.hn.lookback_days`, consistent with `GitHubCollector.fetch()`'s existing "always fetch current state" pattern noted in RESEARCH.md.

## Deviations from Plan

None — plan executed exactly as written. Task 2's stated verify command (`pytest tests/test_collect_hn.py -x`) could not literally run until Task 3's test file existed (the plan sequences implementation before tests); I confirmed Task 2 with a syntax check and a live import/instantiation check against the project's `.venv`, then ran the full `pytest tests/test_collect_hn.py -x` suite for real after Task 3 landed — both tasks are covered by the actual green test run recorded above. This is a minor plan-sequencing note, not a scope or architectural deviation.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. No `GITHUB_TOKEN` or any auth token is referenced (unauthenticated public Algolia API, confirmed via `grep -n GITHUB_TOKEN techtrend/collectors/hn.py` returning nothing).

## Next Phase Readiness
- `HNCollector` is complete and tested in isolation; ready for the Wave 3 integration plan (03-06) to add it to `techtrend/collectors/registry.py`'s `COLLECTORS` list.
- No changes made to `registry.py`, `score.py`, `normalize.py`, `config.py`, `http.py`, or the dashboard — this plan's scope was confined to the HN collector module and its tests, per the plan's explicit boundary.
- Full test suite verified green for this plan's tests (`pytest tests/test_collect_hn.py -x`, 7 passed) and no regression in the existing GitHub collector suite (`pytest tests/test_collect_github.py -q`, 16 passed).

---
*Phase: 03-source-breadth-discourse-downloads-changelogs*
*Completed: 2026-08-22*

## Self-Check: PASSED

All created files verified present on disk; all three task commit hashes (`62a1093`, `ccb48dd`, `2494bb9`) verified present in git history.
