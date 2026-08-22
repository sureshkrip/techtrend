---
phase: 03-source-breadth-discourse-downloads-changelogs
plan: 06
subsystem: ingestion
tags: [feedparser, collectors, registry, atom, rss, changelog]

# Dependency graph
requires:
  - phase: 03-source-breadth-discourse-downloads-changelogs
    provides: "03-01 normalize.py PRIMARY_METRIC['changelog']->'releases' + ChangelogMomentum identity converter; 03-02 config.py ChangelogFeed model; 03-04 HNCollector; 03-05 NpmCollector/PyPiCollector"
provides:
  - "ChangelogCollector (source_id='changelog') parsing curated Atom/RSS feeds via feedparser into metrics={'releases': N} (D3-3)"
  - "COLLECTORS registry grown to 5 entries: github, hn, npm, pypi, changelog -- all Phase-3 sources reachable end-to-end via run_collection"
  - "Updated registry-count test asserting the full 5-source_id set"
affects: [phase-3-remaining-plans, score.py-consumers, dashboard-multi-source-rendering]

# Tech tracking
tech-stack:
  added: ["feedparser==6.0.14"]
  patterns:
    - "Collector construction stays side-effect-free (config resolved lazily in fetch()) -- ChangelogCollector follows GitHubCollector/HNCollector/NpmCollector's established shape"
    - "Optional `now` injection seam on ChangelogCollector/count_entries_in_window for deterministic window-boundary tests against a static fixture file (mirrors the `transport`/`cache_db_path` injection seams elsewhere)"

key-files:
  created:
    - techtrend/collectors/changelog.py
    - tests/test_collect_changelog.py
    - tests/fixtures/changelog/sample_feed.xml
  modified:
    - pyproject.toml
    - techtrend/collectors/registry.py
    - tests/test_collect_github.py

key-decisions:
  - "feedparser==6.0.14 package-legitimacy checkpoint (RESEARCH [SUS] false-positive) approved by owner before install, per dependency_checkpoint pre-approval in this plan's execution context"
  - "Added an optional `now` parameter to ChangelogCollector and count_entries_in_window so window-boundary tests against a static fixture file stay deterministic forever, rather than drifting as wall-clock time passes against hardcoded fixture dates -- not in the original plan text but required to satisfy the plan's own 'deterministic window assertion' + 'no live network call' requirements together"

patterns-established:
  - "ChangelogCollector has no httpx.Client seam (unlike every other collector) -- feedparser.parse() manages its own I/O directly from a URL or local path, so there is nothing to inject beyond the feed URL itself"

requirements-completed: [COLL-05]

coverage:
  - id: D1
    description: "ChangelogCollector parses curated Atom/RSS feeds via feedparser and counts entries within the trailing window into metrics={'releases': N}"
    requirement: "COLL-05"
    verification:
      - kind: unit
        ref: "tests/test_collect_changelog.py#test_count_entries_in_window_counts_only_entries_within_lookback"
        status: pass
      - kind: unit
        ref: "tests/test_collect_changelog.py#test_fetch_parses_local_fixture_feed_and_counts_in_window_releases"
        status: pass
    human_judgment: false
  - id: D2
    description: "Narrow lookback window excludes older entries (boundary case)"
    requirement: "COLL-05"
    verification:
      - kind: unit
        ref: "tests/test_collect_changelog.py#test_count_entries_in_window_narrow_lookback_excludes_older_entries"
        status: pass
    human_judgment: false
  - id: D3
    description: "normalize() maps release count into metrics={'releases': N} with source='changelog' and source_native_id=feed label"
    requirement: "COLL-05"
    verification:
      - kind: unit
        ref: "tests/test_collect_changelog.py#test_normalize_maps_release_count_into_metrics"
        status: pass
    human_judgment: false
  - id: D4
    description: "A dead/malformed feed is logged and skipped rather than aborting the whole collector run"
    requirement: "COLL-05"
    verification:
      - kind: unit
        ref: "tests/test_collect_changelog.py#test_fetch_skips_dead_feed_not_whole_run"
        status: pass
    human_judgment: false
  - id: D5
    description: "All five collectors (github, hn, npm, pypi, changelog) are registered in COLLECTORS and satisfy the Collector protocol; orchestrator never branches on source_id"
    requirement: "COLL-05"
    verification:
      - kind: unit
        ref: "tests/test_collect_github.py#test_collectors_registry_has_all_five_phase3_entries_satisfying_protocol"
        status: pass
      - kind: unit
        ref: "full suite: pytest -q (200 passed)"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-08-22
status: complete
---

# Phase 3 Plan 06: Vendor Changelog Collector + Full Registry Wiring Summary

**`ChangelogCollector` counts feedparser-parsed Atom/RSS entries-in-window into `metrics={"releases": N}`, and `COLLECTORS` grows from 1 to 5 entries — github, hn, npm, pypi, changelog — completing Phase 3's end-to-end wiring.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-08-22
- **Tasks:** 4 (1 checkpoint + 3 auto)
- **Files modified:** 6 (pyproject.toml, uv.lock, techtrend/collectors/changelog.py, techtrend/collectors/registry.py, tests/test_collect_changelog.py, tests/fixtures/changelog/sample_feed.xml, tests/test_collect_github.py)

## Accomplishments
- `feedparser==6.0.14` installed after the human legitimacy checkpoint (pre-approved by owner) cleared
- `ChangelogCollector` (`source_id="changelog"`) parses curated `config.changelogs` feed URLs, counts entries whose `published_parsed`/`updated_parsed` falls within the trailing lookback window, and normalizes to `metrics={"releases": N}` via `normalize.PRIMARY_METRIC['changelog']`/`ChangelogMomentum` (both delivered by 03-01, used read-only)
- Dead or malformed feeds (`parsed.bozo`) are logged and skipped, never aborting the collector run
- `COLLECTORS` registry wired to all four new Phase-3 collectors (`HNCollector`, `NpmCollector`, `PyPiCollector`, `ChangelogCollector`) alongside `GitHubCollector` — 5 entries total, all satisfying the `Collector` protocol
- Registry-count test updated and renamed (`test_collectors_registry_has_all_five_phase3_entries_satisfying_protocol`) to assert `len(COLLECTORS) == 5` and the full `{"github","hn","npm","pypi","changelog"}` source_id set
- Full test suite (`pytest -q`) run as the Wave-3 merge gate: **200 passed, 0 failed**

## Task Commits

Each task was committed atomically:

1. **Task 1: Package-legitimacy checkpoint for feedparser** - checkpoint, pre-approved by owner in the execution prompt (no code change)
2. **Task 2: Add feedparser dependency and implement ChangelogCollector** - `16cf2f4` (feat)
3. **Task 3: Changelog fixture + collector tests** - `f80c9a9` (test)
4. **Task 4: Register all four new collectors and update the registry-count test** - `70bffa5` (feat)

_No metadata/docs commit was made for this SUMMARY per explicit orchestrator instruction (SUMMARY.md/STATE.md/ROADMAP.md are intentionally left uncommitted for this plan)._

## Files Created/Modified
- `techtrend/collectors/changelog.py` - `ChangelogCollector`: feedparser-based fetch() + normalize() implementing the Collector protocol
- `techtrend/collectors/registry.py` - `COLLECTORS` grown to 5 entries (github, hn, npm, pypi, changelog)
- `tests/test_collect_changelog.py` - in-window counting, boundary case, per-feed failure isolation, normalize, protocol conformance
- `tests/fixtures/changelog/sample_feed.xml` - static Atom fixture with 4 entries at fixed dates
- `tests/test_collect_github.py` - registry-count assertion updated 1 -> 5, source_id set assertion
- `pyproject.toml` / `uv.lock` - `feedparser==6.0.14` dependency added and locked

## Decisions Made
- Added an optional `now` parameter to `ChangelogCollector.__init__` and `count_entries_in_window()` (defaulting to `datetime.now(UTC)` in production) purely as a test-injection seam, so the window-boundary assertions against the static fixture file stay deterministic indefinitely rather than depending on wall-clock proximity to hardcoded fixture dates. This mirrors the existing `transport`/`cache_db_path` injection pattern used elsewhere in the collectors (`http.py::build_client`).
- feedparser legitimacy checkpoint: approved per explicit owner sign-off already present in this plan's execution instructions (feedparser is the long-standing canonical Universal Feed Parser, kurtmckee/feedparser, already named in CLAUDE.md's supporting-libs table). No further human interaction was required or solicited.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added deterministic-time test injection seam**
- **Found during:** Task 3 (changelog fixture + tests)
- **Issue:** The plan's own instructions require both "no live network call in tests" (a static fixture file with hardcoded entry dates) AND deterministic window-boundary assertions. `count_entries_in_window`'s original signature (mirroring RESEARCH.md's example) computed the cutoff from `datetime.now(UTC)` with no way to pin it, which would make assertions against a static fixture's hardcoded dates silently drift out of window as real time passes — a latent test-flakiness bug, not a hypothetical one.
- **Fix:** Added an optional `now: datetime | None = None` parameter to `count_entries_in_window()` and threaded an equivalent `now` constructor param through `ChangelogCollector`, defaulting to real current time when omitted (production behavior unchanged).
- **Files modified:** `techtrend/collectors/changelog.py`, `tests/test_collect_changelog.py`
- **Verification:** `pytest tests/test_collect_changelog.py -x` (7 passed); full suite green
- **Committed in:** `16cf2f4` (collector) and `f80c9a9` (tests)

---

**Total deviations:** 1 auto-fixed (1 missing critical / testability)
**Impact on plan:** Necessary to satisfy the plan's own stated determinism requirement without live network access. No scope creep — production `fetch()` behavior (default to real "now") is unchanged from what the plan specified.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. `feedparser` feed URLs are curated in `config/tracked.toml` by the owner (D3-4), not user-facing.

## Next Phase Readiness
- All five Phase-3 collectors (github, hn, npm, pypi, changelog) are registered and reachable end-to-end via `run_collection` — the orchestrator still never branches on `source_id`.
- Full test suite green (200 passed) confirms no regression across the whole Wave-1/Wave-2/Wave-3 integration.
- Remaining Phase-3 scope (if any: dashboard label generalization, unauthenticated http client wiring per D3-5, cross-source calibration follow-up per D3-2) is out of this plan's boundary and tracked separately in ROADMAP/REQUIREMENTS.

---
*Phase: 03-source-breadth-discourse-downloads-changelogs*
*Completed: 2026-08-22*

## Self-Check: PASSED

All created files and commit hashes verified present:
- FOUND: techtrend/collectors/changelog.py
- FOUND: tests/test_collect_changelog.py
- FOUND: tests/fixtures/changelog/sample_feed.xml
- FOUND: techtrend/collectors/registry.py
- FOUND: .planning/phases/03-source-breadth-discourse-downloads-changelogs/03-06-SUMMARY.md
- FOUND commit: 16cf2f4
- FOUND commit: f80c9a9
- FOUND commit: 70bffa5
