---
phase: 01-foundation-first-signal-github-scored-and-visible
plan: 03
subsystem: collectors
tags: [httpx, hishel, tenacity, pydantic, sqlite, github-api, plugin-architecture]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Four-table SQLite schema (entities/snapshots/scores/run_manifest) with docs_url/docs_url_kind columns pre-built, techtrend.db.connection, techtrend.config.load_config(), tests/conftest.py fixtures, recorded GitHub fixtures"
  - phase: 01-02
    provides: "techtrend/ingest.py --fixture offline path, FastAPI dashboard reading entities/snapshots via query_ranked, D-15 docs-link honesty pattern already reflected in the template"
provides:
  - "techtrend/collectors/{base,http,github,registry}.py — the Collector plugin seam: CollectedItem contract, hishel-cached+tenacity-backed HTTP client, GitHubCollector (discovery+metadata+releases+README), COLLECTORS registry"
  - "techtrend/pipeline/{identity,snapshot,docs_link,orchestrator}.py — source-agnostic resolve_entity()/write_snapshot()/resolve_docs_url()/run_collection() driving entities/snapshots/run_manifest from any Collector"
  - "techtrend/ingest.py (no-flag path) — live GitHub collection wired through run_collection(), --fixture path unchanged"
affects: [scoring-engine, health-strip, dashboard, phase-3-collectors]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Collector Protocol (runtime_checkable) + CollectedItem pydantic v2 contract — the only structural coupling between a source module and the pipeline (COLL-06)"
    - "hishel SyncCacheTransport/SyncSqliteStorage wrapping httpx, verified against installed hishel 1.3.0's actual constructor signatures rather than RESEARCH.md's unverified assumption"
    - "tenacity retry_if_exception(is_retryable) predicate distinguishing transient (5xx, 403-with-remaining-0) from permanent (403-without-header, 404) GitHub failures — never a hand-rolled sleep loop"
    - "Per-collector failure isolation in run_collection(): one dead source records 'failed' and the loop continues, never aborting the run (Pitfall 1 / T-01-14)"
    - "success/zero_items/failed as three distinct run_manifest statuses — a source silently returning nothing is never conflated with a healthy run"
    - "docs_url/docs_url_kind resolved and re-written on every resolve_entity() call (insert or update) so a repo that later gains a homepage improves its link on the next run"

key-files:
  created:
    - techtrend/collectors/base.py
    - techtrend/collectors/http.py
    - techtrend/collectors/github.py
    - techtrend/collectors/registry.py
    - techtrend/pipeline/__init__.py
    - techtrend/pipeline/identity.py
    - techtrend/pipeline/snapshot.py
    - techtrend/pipeline/docs_link.py
    - techtrend/pipeline/orchestrator.py
    - tests/test_idempotency.py
    - tests/test_docs_link.py
  modified:
    - techtrend/collectors/__init__.py
    - techtrend/ingest.py
    - tests/test_collect_github.py
    - tests/test_health.py

key-decisions:
  - "Resumed from a dead executor's partial, uncommitted Task 1 work (base.py, http.py, and — discovered on inspection — github.py and registry.py, one file beyond what the resume brief described). Reviewed all five files against the plan's acceptance criteria before continuing; all were correct and preserved verbatim except two docstring-only false-positive-grep fixes (see Deviations)."
  - "Verified hishel's installed 1.3.0 constructor signatures directly via inspect.signature() before trusting the preserved http.py — confirmed SyncCacheTransport(next_transport, storage, policy) and SyncSqliteStorage(database_path=...) match exactly, correcting RESEARCH.md's Assumption A3"
  - "Added a cache_db_path override parameter to build_client() (not in the original plan text) so tests never share hishel cache state with the real .hishel/ directory — without it, a conditional-request test's outcome would depend on whatever ETag a prior local run happened to cache, making the test order-dependent and flaky"
  - "Added @runtime_checkable to the Collector Protocol so tests can isinstance()-check COLLECTORS entries against the protocol per the plan's stated acceptance criterion ('every element satisfies the Collector protocol') — Python's Protocol raises TypeError on isinstance without this decorator"
  - "run_collection()/record_stage() take a datetime.date for run_date (matching Collector.fetch(since: date)'s signature) and convert to an ISO string internally for run_manifest/snapshots — keeps the date/string boundary at one place rather than threading string dates through the collector protocol"
  - "The COLL-09-empty rejection path (null/empty source_native_id) is proven at the resolve_entity() unit level directly, rather than requiring a full run_collection() round-trip — simpler and equally conclusive since resolve_entity() is the single call site the orchestrator uses"

patterns-established:
  - "Pattern: every docstring referencing an acceptance-criteria grep target names the concept, never the literal substring being grep-counted (e.g., 'the auth token env var' not 'GITHUB_TOKEN', 'no source name literal' not 'github') — a repeat of the same false-positive-grep-in-docstring bug documented in 01-02's SUMMARY, now avoided by convention"
  - "Pattern: fake Collector test doubles (_FakeCollector) implementing fetch()/normalize() directly in the test file — no live network call, no dependency on the real GitHubCollector, proves orchestrator behavior in isolation"

requirements-completed: [COLL-01, COLL-06, COLL-07, COLL-08, COLL-09, DATA-01, DATA-02, DATA-05, DASH-05, HEALTH-01]

coverage:
  - id: D1
    description: "Collector plugin seam: Collector protocol + CollectedItem contract, GitHubCollector implementing discovery/metadata/releases/README fetch over an authenticated, cached, backoff-protected client, COLLECTORS as the single extension point"
    requirement: "COLL-06"
    verification:
      - kind: unit
        ref: "tests/test_collect_github.py::test_collectors_registry_has_exactly_one_entry_satisfying_protocol"
        status: pass
      - kind: unit
        ref: "tests/test_collect_github.py::test_normalize_maps_metadata_fixture_onto_collected_item"
        status: pass
    human_judgment: false
  - id: D2
    description: "Deterministic admission gate (D-01/D-03/D-04): seed, allowlisted topic, keyword fallback, and force-include all admit; force-exclude wins even over a topic match"
    requirement: "COLL-01"
    verification:
      - kind: unit
        ref: "tests/test_collect_github.py::test_admit_repo_seed_list_repo_admitted"
        status: pass
      - kind: unit
        ref: "tests/test_collect_github.py::test_admit_repo_force_excluded_wins_over_topic_match"
        status: pass
    human_judgment: false
  - id: D3
    description: "COLL-07 retry predicate: 5xx and 403-with-remaining-0 are transient (retried); 403-without-header and 404 are permanent (not retried)"
    requirement: "COLL-07"
    verification:
      - kind: unit
        ref: "tests/test_collect_github.py::test_is_retryable_403_permission_denied_not_retried"
        status: pass
      - kind: unit
        ref: "tests/test_collect_github.py::test_is_retryable_404_not_retried"
        status: pass
    human_judgment: false
  - id: D4
    description: "COLL-08 conditional requests: a repeated repo-metadata request issues an If-None-Match conditional GET and a 304 resolves as a clean cache hit, never surfaced as an error"
    requirement: "COLL-08"
    verification:
      - kind: unit
        ref: "tests/test_collect_github.py::test_repo_metadata_replayed_twice_issues_conditional_request_and_304_is_cache_hit"
        status: pass
    human_judgment: false
  - id: D5
    description: "Entity resolution: match-or-create keyed on (source, source_native_id), rename-safe, order-independent, rejects null/empty identity keys without raising (DATA-01, COLL-09)"
    requirement: "COLL-09"
    verification:
      - kind: unit
        ref: "tests/test_idempotency.py::test_resolve_entity_same_identity_key_yields_one_entities_row"
        status: pass
      - kind: unit
        ref: "tests/test_idempotency.py::test_resolve_entity_renamed_repo_same_native_id_updates_existing_row"
        status: pass
      - kind: unit
        ref: "tests/test_idempotency.py::test_resolve_entity_null_source_native_id_rejected_without_error"
        status: pass
      - kind: unit
        ref: "tests/test_idempotency.py::test_resolve_entity_order_independent"
        status: pass
    human_judgment: false
  - id: D6
    description: "Append-only snapshot upsert, and a full collection re-run against the same fixtures/run_date leaves entity and snapshot counts unchanged (DATA-02, DATA-05)"
    requirement: "DATA-05"
    verification:
      - kind: unit
        ref: "tests/test_idempotency.py::test_write_snapshot_upsert_replaces_same_day_value"
        status: pass
      - kind: unit
        ref: "tests/test_idempotency.py::test_run_collection_twice_same_fixture_same_run_date_is_idempotent"
        status: pass
    human_judgment: false
  - id: D7
    description: "Source-agnostic orchestrator: no source-name branch (grep-verified), per-collector failure isolation, success/zero_items/failed distinction, run_manifest upsert-not-append on (run_date, stage)"
    requirement: "HEALTH-01"
    verification:
      - kind: unit
        ref: "tests/test_health.py::test_failing_collector_records_failed_status_and_does_not_abort_run"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_zero_items_flagged_not_silent"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_no_collector_produces_items_still_writes_one_row_per_collector"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_record_stage_same_run_date_and_stage_replaces_not_appends"
        status: pass
      - kind: other
        ref: "grep -c github techtrend/pipeline/orchestrator.py returns 0"
        status: pass
    human_judgment: false
  - id: D8
    description: "Deterministic docs-link fallback chain: homepage wins outright, else first matching README link in document order, else the bare repo URL honestly labeled 'repo' (never relabeled)"
    requirement: "DASH-05"
    verification:
      - kind: unit
        ref: "tests/test_docs_link.py::test_homepage_wins_even_when_readme_also_has_a_matching_link"
        status: pass
      - kind: unit
        ref: "tests/test_docs_link.py::test_empty_homepage_and_no_matching_readme_link_falls_back_to_repo_url"
        status: pass
      - kind: unit
        ref: "tests/test_docs_link.py::test_multiple_matching_readme_links_returns_first_in_document_order"
        status: pass
      - kind: unit
        ref: "tests/test_docs_link.py::test_kind_is_always_exactly_one_of_three_literals_and_repo_never_relabeled"
        status: pass
    human_judgment: false
  - id: D9
    description: "python -m techtrend.ingest (no flags) attempts live collection and degrades cleanly with a run_manifest 'failed' row and a descriptive error_detail when GITHUB_TOKEN is absent; --fixture path unchanged from 01-02"
    requirement: null
    verification:
      - kind: manual_procedural
        ref: "uv run python -m techtrend.ingest (no GITHUB_TOKEN in environment) — logged WARNING+INFO with .env.example guidance, run_manifest row {status: failed, error_detail: 'GITHUB_TOKEN is not set...'}, exit code 0"
        status: pass
      - kind: manual_procedural
        ref: "uv run python -m techtrend.ingest --fixture — entities row written, docs_url/docs_url_kind NULL as expected (fixture path bypasses the pipeline)"
        status: pass
    human_judgment: true
    rationale: "The live-GitHub-populates-real-data half of this deliverable (entities/snapshots from an actual GitHub response, a second run showing 304s in the log) requires a real GITHUB_TOKEN, which is a user-owned secret not available to this execution session — the degradation path was verified directly, but the happy path with live data needs the user's own token."

duration: 70min
completed: 2026-07-19
status: complete
---

# Phase 01 Plan 03: GitHub Collector, Pipeline, and Docs-Link Resolution Summary

**Live GitHub collection (discovery + metadata + releases + README) over an authenticated hishel-cached, tenacity-backed client, flowing through a source-agnostic identity/snapshot/orchestrator pipeline that records per-source health on every run, with a deterministic homepage-to-repo docs-link fallback chain that never mislabels a bare repo URL as documentation.**

## Performance

- **Duration:** 70 min (resumed session; excludes the dead prior executor's partial work)
- **Started:** 2026-07-19T20:40:00Z (approx, resume)
- **Completed:** 2026-07-19T21:15:00Z
- **Tasks:** 3 (all auto/tdd)
- **Files modified:** 15 (11 new, 4 modified)

## Accomplishments
- Resumed a dead executor's uncommitted Task 1 work — reviewed `techtrend/collectors/{base,http,github,registry}.py` against every plan acceptance criterion, verified hishel's installed 1.3.0 API shape directly via `inspect.signature()`, confirmed the preserved design decisions (source-agnostic `CollectedItem`, `GITHUB_TOKEN` confined to `http.py`, `is_retryable`'s 403/404 boundary, injectable `transport` kwarg) were all correct and kept them
- Filled `tests/test_collect_github.py` with 12 tests: `admit_repo` (D-01/D-03/D-04), `is_retryable` (COLL-07 boundary), a real `httpx.MockTransport`-driven proof that a repeated repo-metadata request issues a conditional `If-None-Match` GET and resolves a 304 as a clean cache hit (COLL-08), `normalize()`'s numeric-id mapping (COLL-09), and registry/protocol conformance
- Built `techtrend/pipeline/{identity,snapshot,orchestrator}.py`: `resolve_entity()` match-or-create keyed on `(source, source_native_id)`, `write_snapshot()` append-only upsert with a `source_kind` parameter for 01-05's future backfill writes, and `run_collection()`/`record_stage()` driving `run_manifest` with per-collector failure isolation and a `success`/`zero_items`/`failed` three-way distinction
- Wrote 12 tests across `tests/test_idempotency.py` and `tests/test_health.py` covering DATA-01/COLL-09 adjacency-empty-ordering and HEALTH-01's failure-isolation and upsert-not-append guarantees
- Built `techtrend/pipeline/docs_link.py`: the strictly-ordered `resolve_docs_url()` chain (homepage → matching README link in document order → honest `'repo'` fallback), wired into `identity.py` so every `resolve_entity()` call also resolves and (re-)writes `docs_url`/`docs_url_kind`
- Wired `techtrend/ingest.py`'s default (no-flag) path to `run_collection()` against the `COLLECTORS` registry, leaving `--fixture` untouched; manually verified both the no-token degradation path (clean `run_manifest` `'failed'` row with actionable guidance, exit 0, no traceback) and the unaffected `--fixture` offline path

## Task Commits

1. **Task 1: Collector plugin seam and the GitHub collector** - `3211c75` (feat)
2. **Task 2: Identity resolution, snapshot upsert, and the source-agnostic orchestrator** - `90c07ed` (feat)
3. **Task 3: Deterministic docs-link resolution with honest labeling** - `42cd2ad` (feat)

## Files Created/Modified
- `techtrend/collectors/base.py` - `Collector` (`@runtime_checkable` Protocol) + `CollectedItem` pydantic v2 model (added `runtime_checkable` this session; rest preserved from the dead executor)
- `techtrend/collectors/http.py` - `build_client()` (hishel `SyncCacheTransport`/`SyncSqliteStorage`, verified against installed hishel 1.3.0) + `is_retryable()`; added `cache_db_path` override for test isolation
- `techtrend/collectors/github.py` - `GitHubCollector`: `admit_repo()` D-01/D-03/D-04 gate, search discovery (topics + keyword passes), per-repo metadata/releases/README fetch with tenacity backoff, `normalize()` (preserved verbatim except a docstring wording fix)
- `techtrend/collectors/registry.py` - `COLLECTORS = [GitHubCollector()]` (preserved verbatim)
- `techtrend/pipeline/identity.py` - `resolve_entity()`: match-or-create, null-id rejection, now also resolves+writes `docs_url`/`docs_url_kind`
- `techtrend/pipeline/snapshot.py` - `write_snapshot()`: append-only upsert with `source_kind` parameter
- `techtrend/pipeline/orchestrator.py` - `record_stage()` + `run_collection()`: run_manifest upsert, per-collector failure isolation, `StageResult` dataclass
- `techtrend/pipeline/docs_link.py` - `resolve_docs_url()` + `DOCS_PATTERNS`: the D-15 fallback chain
- `techtrend/ingest.py` - default (no-flag) path now calls `run_collection()` against `COLLECTORS`; `--fixture` unchanged
- `tests/test_collect_github.py` - 12 tests (filled from placeholder)
- `tests/test_idempotency.py` - 8 tests (new)
- `tests/test_health.py` - 4 tests (filled from placeholder)
- `tests/test_docs_link.py` - 5 tests (new)

## Decisions Made
- The resume brief described three preserved files (`__init__.py`, `base.py`, `http.py`); on-disk inspection found five (`github.py` and `registry.py` also existed, fully implemented and correct). Reviewed all five against every Task 1 acceptance criterion before proceeding rather than trusting the brief's file list — both extra files matched the plan exactly and needed only the same docstring-literal fix already seen elsewhere.
- Added `@runtime_checkable` to `Collector` and a `cache_db_path` override to `build_client()` — both minimal, additive fixes required to satisfy the plan's own stated test requirements (isinstance-checking the protocol; isolating hishel cache state between test runs) without altering any of the preserved design decisions.
- `run_collection`/`record_stage` take `run_date: date` (matching `Collector.fetch`'s `since: date` parameter) rather than a pre-formatted string, converting to ISO format once, internally.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed false-positive grep matches in module docstrings**
- **Found during:** Task 1 and Task 2 acceptance-criteria verification
- **Issue:** `techtrend/collectors/github.py`'s docstring explained "`GITHUB_TOKEN` is never read here" (literal substring match broke `grep -c 'GITHUB_TOKEN' techtrend/collectors/github.py` returning `0`), and `techtrend/pipeline/orchestrator.py`'s docstring said "a grep for the literal `github` ... must find nothing" (literal substring match broke `grep -c 'github' techtrend/pipeline/orchestrator.py` returning `0`) — the same class of bug documented as Deviation #1 in the 01-02 SUMMARY
- **Fix:** Reworded both docstrings to describe the same guarantee without using the literal substring being grep-counted
- **Files modified:** `techtrend/collectors/github.py`, `techtrend/pipeline/orchestrator.py`
- **Verification:** Both greps return `0`; `ruff check .` and full test suite still pass
- **Committed in:** `3211c75` (Task 1), `90c07ed` (Task 2)

**2. [Rule 3 - Blocking] Added `@runtime_checkable` to the `Collector` Protocol**
- **Found during:** Task 1, writing `test_collectors_registry_has_exactly_one_entry_satisfying_protocol`
- **Issue:** The plan's acceptance criterion requires proving "every element satisfies the `Collector` protocol"; Python's `Protocol` raises `TypeError: Instance and class checks can only be used with @runtime_checkable protocols` on a bare `isinstance()` check, blocking the test
- **Fix:** Added `@runtime_checkable` to `Collector` in `base.py`
- **Files modified:** `techtrend/collectors/base.py`
- **Verification:** `tests/test_collect_github.py::test_collectors_registry_has_exactly_one_entry_satisfying_protocol` passes
- **Committed in:** `3211c75` (Task 1)

**3. [Rule 3 - Blocking] Added a `cache_db_path` override to `build_client()`**
- **Found during:** Task 1, writing the COLL-08 conditional-request test
- **Issue:** `build_client()` hardcoded `.hishel/github.db` as the cache storage path. A test exercising the real hishel cache layer against a `MockTransport` would persist cache state to that shared file across every local test run — a prior run's cached ETag for the same mock URL would make the "second request is conditional" assertion order-dependent and flaky, not a deterministic unit test
- **Fix:** Added an optional `cache_db_path: Path | None` parameter defaulting to the existing module constant; tests pass a `tmp_path`-scoped path
- **Files modified:** `techtrend/collectors/http.py`
- **Verification:** `tests/test_collect_github.py::test_repo_metadata_replayed_twice_issues_conditional_request_and_304_is_cache_hit` passes deterministically on repeat runs
- **Committed in:** `3211c75` (Task 1)

---

**Total deviations:** 3 auto-fixed (2 Rule 1 docstring/grep bugs, 1 Rule 3 blocking test-infrastructure gap)
**Impact on plan:** All three were required to satisfy the plan's own stated acceptance criteria and test behaviors. No scope creep, no preserved design decision altered.

## Issues Encountered
None beyond the auto-fixed items documented above. The dead prior executor's partial work (`base.py`, `http.py`, `github.py`, `registry.py`) was reviewed line-by-line against the plan and found correct in full — no rework was needed on the substance of any preserved file.

## User Setup Required
A real `GITHUB_TOKEN` is required to exercise the live-collection happy path end-to-end (populating `entities`/`snapshots` from actual GitHub data and observing 304 responses on a second run). Without it, `python -m techtrend.ingest` degrades cleanly: logs a WARNING with `.env.example` guidance, writes a `run_manifest` row with `status='failed'` and a descriptive `error_detail`, and exits 0 rather than crashing. See `.env.example` (created in 01-01) for the variable name and required scope (fine-grained personal access token, public-repo read access).

## Next Phase Readiness
- `python -m techtrend.ingest` (no flags) is the live collection entry point; `--fixture` remains the offline dev path, unaffected by this plan.
- The collector plugin seam (`Collector` protocol, `CollectedItem` contract, `COLLECTORS` registry) is proven structurally (grep-verified no source-name branch in the orchestrator) and ready for Phase 3's HN/npm/PyPI/RSS collectors to plug into with zero pipeline changes.
- `entities.docs_url`/`docs_url_kind` are now populated by the live path; the dashboard (01-02) already renders the honest "Repo" fallback label for `docs_url_kind='repo'` with zero template changes needed.
- `scores` table remains empty — plan 01-04 (Wilson-bounded scoring) is next, reading `snapshots` written by this plan's `write_snapshot()`.
- No blockers. `uv run pytest -q` is green (40 passed, 2 skipped — remaining skips belong to plans 01-04/01-06) and `uv run ruff check .` is clean.

---
*Phase: 01-foundation-first-signal-github-scored-and-visible*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 13 created/modified files found on disk; all three task commits (`3211c75`, `90c07ed`, `42cd2ad`) found in git log.
