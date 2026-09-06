---
phase: quick-260906-nqc
plan: 01
subsystem: ui
tags: [fastapi, jinja2, htmx, postgres, psycopg3, dashboard]

# Dependency graph
requires:
  - phase: quick-260825-twr
    provides: entities.source column already SELECTed in _QUERY_RANKED_SQL for per-row link labeling
provides:
  - SOURCE_KEYS allow-list mapping github/hn/packages/changelog URL keys to entities.source value sets
  - query_ranked source parameter + applied_source 3-tuple return, bound `= ANY(%(sources)s)` predicate
  - GET / source query param threaded through app.py to template context
  - partials/source_tabs.html top tab row (All/GitHub/Hacker News/Packages/Changelogs)
  - source carry-through on every sidebar section link and table sort header
affects: [dashboard, server-routes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Second allow-list-key -> server-side value-set table -> bound array param pattern (SOURCE_KEYS mirrors SORT_KEYS/section_filter discipline)"
    - "Multi-axis htmx filter composition: every control (sort/section/source) carries the other two so none silently resets another (Pitfall #5)"

key-files:
  created:
    - techtrend/web/templates/partials/source_tabs.html
  modified:
    - techtrend/server/queries.py
    - techtrend/server/app.py
    - techtrend/web/templates/dashboard.html
    - techtrend/web/templates/partials/sidebar.html
    - techtrend/web/templates/partials/table.html
    - tests/test_dashboard.py

key-decisions:
  - "Packages tab combines npm + pypi into one group (CONTEXT.md locked decision) rather than separate tabs, since prod has only ~4 npm + ~5 pypi items"
  - "query_section_counts stays source-independent (no source arg, no narrowing) -- matches existing precedent that it already ignores the section filter too"
  - "Unrecognized ?source= value falls back to All (no predicate) exactly mirroring unrecognized ?sort= falling back to DEFAULT_SORT"

patterns-established:
  - "SOURCE_KEYS: dict[str, list[str]] as the source analogue of SORT_KEYS -- URL carries only an allow-list key, raw source values live server-side, bound as a psycopg3 array param for ANY()"

requirements-completed: [DASH-02, T-01-06, T-01-29, D-17]

coverage:
  - id: D1
    description: "Default/no-source view shows the unchanged unfiltered list across all 5 sources"
    requirement: "DASH-02"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_default_all_view_shows_rows_from_every_source"
        status: pass
    human_judgment: false
  - id: D2
    description: "Single-source tabs (GitHub/Hacker News/Changelogs) narrow the table to that source only"
    requirement: "DASH-02"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_single_source_tabs_narrow_to_that_source_only"
        status: pass
    human_judgment: false
  - id: D3
    description: "Packages tab combines npm + pypi into one group, excluding other sources"
    requirement: "DASH-02"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_packages_tab_combines_npm_and_pypi_and_excludes_others"
        status: pass
    human_judgment: false
  - id: D4
    description: "Source and section filters compose with AND, neither resets the other"
    requirement: "DASH-02"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_source_and_section_filters_compose_with_and"
        status: pass
    human_judgment: false
  - id: D5
    description: "Unrecognized ?source= value falls back to All (no predicate), never reaches SQL as raw text"
    requirement: "T-01-06"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_unknown_source_falls_back_to_all"
        status: pass
    human_judgment: false
  - id: D6
    description: "Active source round-trips on every sort header and section link"
    requirement: "T-01-29"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_active_source_round_trips_on_sort_headers_and_section_links"
        status: pass
    human_judgment: false
  - id: D7
    description: "Source values are bound as a SQL array parameter, never string-interpolated"
    requirement: "D-17"
    verification:
      - kind: unit
        ref: "queries.py source_filter = 'AND entities.source = ANY(%(sources)s)' with params['sources'] as a Python list"
        status: pass
    human_judgment: false
  - id: D8
    description: "Top tab row renders correctly and visually matches sidebar pattern in the browser"
    verification: []
    human_judgment: true
    rationale: "Automated tests confirm template parsing, HTML structure, and filter behavior via TestClient, but final visual placement/styling of the tab row was not spot-checked in a live browser session (deferred per plan's optional manual-check note)."

duration: 5min
completed: 2026-09-06
status: complete
---

# Quick Task 260906-nqc: Add a dashboard source filter Summary

**Top source-tab row (All / GitHub / Hacker News / Packages / Changelogs) added to the dashboard, filtering `query_ranked` via a bound allow-list `SOURCE_KEYS` array parameter that composes with the existing section filter and sort.**

## Performance

- **Duration:** ~5 min (17:12:13 -> 17:17:00, three task commits)
- **Started:** 2026-09-06T17:12:13-04:00
- **Completed:** 2026-09-06T17:17:00-04:00
- **Tasks:** 3
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- `SOURCE_KEYS` allow-list (github/hn/packages/changelog) added to `queries.py`, mapping each URL key to its concrete `entities.source` value set; `query_ranked` now accepts `source`, applies `AND entities.source = ANY(%(sources)s)` only for recognized keys, and returns `applied_source` alongside `applied_sort`
- `GET /` route in `app.py` threads `source` through to `query_ranked` and into the template context, mirroring the existing `section` handling
- New `partials/source_tabs.html` renders the five-tab row above the table, outside `#table-body`, so it survives every htmx swap
- Every sidebar section link and every table sort header now carries `&source={{ source or '' }}`, so re-sectioning or re-sorting never resets the active source tab
- 6 new fixture-backed tests cover the default/all view, single-source narrowing, the npm+pypi packages group, source+section AND composition, unknown-source fallback, and active-source round-trip on links

## Task Commits

Each task was committed atomically:

1. **Task 1: Add source allow-list + bound-param filter to the query and route layer** - `f150810` (feat)
2. **Task 2: Add the top source-tab row and carry `source` through every existing control** - `bfba207` (feat)
3. **Task 3: Fixture-backed tests for source filtering, composition, fallback, and link round-trip** - `5489c51` (test)

_Note: This quick task's docs commit (SUMMARY.md/STATE.md) is handled separately by the orchestrator, not by this executor._

## Files Created/Modified
- `techtrend/server/queries.py` - `SOURCE_KEYS` allow-dict, `query_ranked(source=...)` with bound `ANY(%(sources)s)` predicate and `applied_source` return, `query_section_counts` docstring note (source-independent)
- `techtrend/server/app.py` - `dashboard(...)` route accepts `source`, threads it to `query_ranked`, exposes `applied_source` in template context
- `techtrend/web/templates/partials/source_tabs.html` - new top tab row partial (All/GitHub/Hacker News/Packages/Changelogs)
- `techtrend/web/templates/dashboard.html` - includes `source_tabs.html` above the table, outside `#table-body`
- `techtrend/web/templates/partials/sidebar.html` - every section link now carries `&source={{ source or '' }}`
- `techtrend/web/templates/partials/table.html` - every sort header carries `&source={{ source or '' }}`; new source-specific empty state branch
- `tests/test_dashboard.py` - 6 new tests for source filtering/composition/fallback/round-trip

## Decisions Made
- Packages tab combines npm + pypi into one group per the locked CONTEXT.md decision (prod volume is small: ~4 npm + ~5 pypi items)
- `query_section_counts` deliberately stays source-independent (no `source` argument added) -- matches the existing precedent that it already ignores the `section` filter too, so sidebar totals never shift as the source tab changes
- Unrecognized `source` values fall back to All (no predicate) exactly mirroring the existing unrecognized-`sort` fallback to `DEFAULT_SORT`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. A pre-existing `ruff` line-length violation on an unrelated line in `tests/test_dashboard.py` (the `_sort_link_html` helper's regex, line 123, predates this task and is out of the current task's scope per the deviation rules' scope boundary) was confirmed via `git stash` to already exist on `main` before this task started; left untouched as out-of-scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Feature is complete and fully tested; no blockers for further dashboard work
- Manual browser spot-check of the tab row's visual placement (optional per plan's `<verification>` block) was not performed in this session -- deferred, matching the project's existing pattern of deferring live-browser UAT items (see STATE.md Deferred Items)

---
*Phase: quick-260906-nqc*
*Completed: 2026-09-06*

## Self-Check: PASSED

All 7 claimed files verified present on disk; all 3 claimed commit hashes (f150810, bfba207, 5489c51) verified present in git log.
