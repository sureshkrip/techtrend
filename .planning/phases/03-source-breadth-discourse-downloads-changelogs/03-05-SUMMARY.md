---
phase: 03-source-breadth-discourse-downloads-changelogs
plan: 05
subsystem: collectors
tags: [httpx, tenacity, pydantic, npm, pypi, pypistats]

requires:
  - phase: 03-source-breadth-discourse-downloads-changelogs
    provides: "03-02: build_public_client/is_retryable_public (http.py), Packages config model (config.py)"
  - phase: 03-source-breadth-discourse-downloads-changelogs
    provides: "03-01: normalize.PRIMARY_METRIC['npm']/['pypi'] = 'downloads'"
provides:
  - NpmCollector + PyPiCollector implementing the Collector protocol over api.npmjs.org and pypistats.org
  - Fixture-backed, network-free test suite for both package collectors
affects: [03-06 (registry wiring for HN/npm/PyPI/changelog collectors)]

tech-stack:
  added: []
  patterns:
    - "Per-package fetch isolation (log + skip on HTTPStatusError/TransportError, mirroring GitHubCollector._discover / HNCollector.fetch)"
    - "Rolling last-week TOTAL stored as the metric_value, not a raw daily rate, so compute_window_gain's last-minus-first delta stays meaningful (RESEARCH.md Pitfall 1)"
    - "Scoped npm package (@org/pkg) slash URL-encoded as %2F for the single-package request"

key-files:
  created:
    - techtrend/collectors/packages.py
    - tests/test_collect_packages.py
    - tests/fixtures/packages/npm_downloads.json
    - tests/fixtures/packages/pypi_recent.json
  modified: []

key-decisions:
  - "npm and PyPI share one module (packages.py, two classes) per D3-1's explicit planner's-call"
  - "Only the slash is percent-encoded for a scoped npm package (quote(package, safe='@')) -- matches RESEARCH.md's exact caveat ('URL-encode the slash as %2F'), not the @ sign"

patterns-established:
  - "Wave 2 collector modules stay registry-free by design -- registry.py wiring is deferred to the Wave 3 integration plan (03-06) to keep parallel collector plans conflict-free"

requirements-completed: [COLL-04]

coverage:
  - id: D1
    description: "NpmCollector.fetch() queries api.npmjs.org/downloads/point/last-week/{pkg} once per configured package, encoding a scoped package's slash as %2F, and isolates per-package fetch failures without aborting the run"
    requirement: "COLL-04"
    verification:
      - kind: unit
        ref: "tests/test_collect_packages.py#test_npm_fetch_issues_one_request_per_package"
        status: pass
      - kind: unit
        ref: "tests/test_collect_packages.py#test_npm_fetch_scoped_package_encodes_slash_as_percent_2f"
        status: pass
      - kind: unit
        ref: "tests/test_collect_packages.py#test_npm_fetch_transport_error_skips_package_not_whole_run"
        status: pass
      - kind: unit
        ref: "tests/test_collect_packages.py#test_npm_fetch_with_no_packages_issues_no_requests"
        status: pass
    human_judgment: false
  - id: D2
    description: "NpmCollector.normalize() maps the rolling last-week downloads total onto CollectedItem(metrics={'downloads': N})"
    requirement: "COLL-04"
    verification:
      - kind: unit
        ref: "tests/test_collect_packages.py#test_npm_normalize_maps_downloads_into_metrics"
        status: pass
      - kind: unit
        ref: "tests/test_collect_packages.py#test_npm_normalize_missing_downloads_defaults_to_zero"
        status: pass
    human_judgment: false
  - id: D3
    description: "PyPiCollector.fetch() queries pypistats.org/api/packages/{pkg}/recent once per configured package and isolates per-package fetch failures without aborting the run"
    requirement: "COLL-04"
    verification:
      - kind: unit
        ref: "tests/test_collect_packages.py#test_pypi_fetch_issues_one_request_per_package"
        status: pass
      - kind: unit
        ref: "tests/test_collect_packages.py#test_pypi_fetch_transport_error_skips_package_not_whole_run"
        status: pass
      - kind: unit
        ref: "tests/test_collect_packages.py#test_pypi_fetch_with_no_packages_issues_no_requests"
        status: pass
    human_judgment: false
  - id: D4
    description: "PyPiCollector.normalize() maps data.last_week (NOT last_day) onto CollectedItem(metrics={'downloads': N}) -- pins the rolling-total semantics (RESEARCH.md Pitfall 1)"
    requirement: "COLL-04"
    verification:
      - kind: unit
        ref: "tests/test_collect_packages.py#test_pypi_normalize_maps_last_week_not_last_day_into_metrics"
        status: pass
      - kind: unit
        ref: "tests/test_collect_packages.py#test_pypi_normalize_missing_data_defaults_to_zero"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both collectors satisfy the Collector protocol with the correct source_id ('npm'/'pypi')"
    requirement: "COLL-04"
    verification:
      - kind: unit
        ref: "tests/test_collect_packages.py#test_npm_collector_satisfies_collector_protocol"
        status: pass
      - kind: unit
        ref: "tests/test_collect_packages.py#test_pypi_collector_satisfies_collector_protocol"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-08-22
status: complete
---

# Phase 3 Plan 5: npm + PyPI Download Collectors Summary

**NpmCollector queries api.npmjs.org's last-week downloads-point endpoint and PyPiCollector queries pypistats.org's recent-downloads endpoint, both per configured package, normalizing into CollectedItem(metrics={"downloads": N}) using the rolling last-week TOTAL (never the raw daily rate) so compute_window_gain's last-minus-first delta stays meaningful -- fully fixture-backed, no live network in tests.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 3
- **Files modified:** 4 (all new)

## Accomplishments
- Recorded npm (`downloads/point/last-week`) and pypistats (`recent`) response fixtures, with the pypistats fixture carrying deliberately distinct `last_day` (120) and `last_week` (3400) values to pin the rolling-total semantics
- Implemented `NpmCollector` + `PyPiCollector` (`techtrend/collectors/packages.py`) sharing one module per D3-1: lazy config/client resolution, per-package fetch, scoped-npm-package `%2F` slash encoding, per-package failure isolation (log + skip), and `normalize()` mapping each to `metrics={"downloads": N}` using the rolling last-week total
- Wrote a fixture-backed, network-free test suite (13 tests) covering per-package fetch, scoped-package encoding, transport-error isolation, empty-package-list no-op, normalize downloads mapping, the last_week-vs-last_day regression pin, missing-data defaulting to 0, and `Collector` protocol conformance for both classes

## Task Commits

Each task was committed atomically:

1. **Task 1: Record npm + PyPI download fixtures** - `1b7c4cd` (test)
2. **Task 2: Implement NpmCollector + PyPiCollector in packages.py** - `4e4c97f` (feat)
3. **Task 3: Package collector tests (fixture-backed, no network)** - `56301a4` (test)

**Plan metadata:** (this commit — docs, not staged with SUMMARY.md/STATE.md/ROADMAP.md per plan constraints)

## Files Created/Modified
- `techtrend/collectors/packages.py` - `NpmCollector` (`source_id = "npm"`) + `PyPiCollector` (`source_id = "pypi"`), both implementing `Collector`, sharing one module
- `tests/test_collect_packages.py` - 13 fixture-backed tests, no live network
- `tests/fixtures/packages/npm_downloads.json` - recorded npm last-week point response
- `tests/fixtures/packages/pypi_recent.json` - recorded pypistats recent response with distinct last_day/last_week values

## Decisions Made
- npm and PyPI share one `packages.py` module (two classes) rather than two separate modules — explicitly the planner's call per D3-1.
- Only the slash in a scoped npm package name is percent-encoded (`urllib.parse.quote(package, safe='@')`), matching RESEARCH.md's exact caveat ("URL-encode the slash as %2F") rather than also encoding the `@` — verified npm's endpoint only requires the slash escaped.
- `since: date` is accepted (protocol conformance) but not used to scope either query beyond the configured package list, consistent with `GitHubCollector`/`HNCollector`'s existing "always fetch current state" pattern.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. No `GITHUB_TOKEN` or any auth token is referenced (unauthenticated public npm/pypistats APIs, confirmed via `grep -n GITHUB_TOKEN techtrend/collectors/packages.py` returning nothing).

## Next Phase Readiness
- `NpmCollector` + `PyPiCollector` are complete and tested in isolation; ready for the Wave 3 integration plan (03-06) to add both to `techtrend/collectors/registry.py`'s `COLLECTORS` list.
- No changes made to `registry.py`, `score.py`, `normalize.py`, `config.py`, `http.py`, or the dashboard — this plan's scope was confined to the package collector module and its tests, per the plan's explicit boundary.
- Full test suite verified green for this plan's tests (`pytest tests/test_collect_packages.py -x`, 13 passed) and no regression in the existing GitHub/HN collector or config suites (`pytest tests/test_collect_packages.py tests/test_collect_github.py tests/test_collect_hn.py tests/test_config.py -q`, 44 passed).

---
*Phase: 03-source-breadth-discourse-downloads-changelogs*
*Completed: 2026-08-22*

## Self-Check: PASSED

All created files verified present on disk; all three task commit hashes (`1b7c4cd`, `4e4c97f`, `56301a4`) verified present in git history.
