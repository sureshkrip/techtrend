---
phase: quick-260825-twr
plan: 01
subsystem: ui
tags: [fastapi, jinja2, htmx, postgres, dashboard]

# Dependency graph
requires:
  - phase: 03-source-breadth
    provides: entities.source column populated for hn/npm/pypi/changelog rows (collectors registered in Phase 3)
provides:
  - Source-branched outbound-link labels in the dashboard table (github/hn/npm/pypi/changelog)
  - Suppressed GitHub-specific second link (Repo/Docs) on non-GitHub rows
  - Source-neutral "Item" name-column header
affects: [dashboard, table.html, queries.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Presentation-layer source branching: SQL selects entities.source, Jinja if/elif chain maps source -> label text, href always stays row['url']"

key-files:
  created: []
  modified:
    - techtrend/server/queries.py
    - techtrend/web/templates/partials/table.html
    - tests/test_dashboard.py

key-decisions:
  - "Second link (Repo/Docs) gates on row['source'] == 'github', not on docs_url presence -- preserves the existing undocumented-GitHub-repo fallback-to-Repo-link test unchanged"
  - "Primary link href stays row['url'] for every source; only the visible label text branches on source"

patterns-established:
  - "Non-GitHub source label map: hn->'View on HN', npm->'View on npm', pypi->'View on PyPI', changelog->'View changelog', github/unknown->'View on GitHub' (default fallback)"

requirements-completed: [DASH-04, DASH-05, D3-5]

coverage:
  - id: D1
    description: "entities.source selected in _QUERY_RANKED_SQL so table.html can branch per-row on source"
    requirement: "DASH-04"
    verification:
      - kind: unit
        ref: "python -c import check: 'entities.source' in _QUERY_RANKED_SQL"
        status: pass
      - kind: integration
        ref: "tests/test_dashboard.py#test_hn_row_shows_view_on_hn_and_no_github_or_repo_docs_link"
        status: pass
    human_judgment: false
  - id: D2
    description: "HN row renders 'View on HN' primary label, no 'View on GitHub', no bogus Repo/Docs second link"
    requirement: "DASH-04"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_hn_row_shows_view_on_hn_and_no_github_or_repo_docs_link"
        status: pass
    human_judgment: false
  - id: D3
    description: "npm/PyPI/changelog rows show source-appropriate primary label and no bogus second link"
    requirement: "DASH-05"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_non_github_sources_show_source_appropriate_primary_label"
        status: pass
    human_judgment: false
  - id: D4
    description: "GitHub rows render unchanged: 'View on GitHub' primary + Docs/Repo second link (documented and undocumented cases)"
    requirement: "DASH-04"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_row_links_source_before_docs_with_honest_label"
        status: pass
    human_judgment: false
  - id: D5
    description: "Name-column header reads 'Item', not 'Repo'"
    requirement: "D3-5"
    verification:
      - kind: integration
        ref: "tests/test_dashboard.py#test_name_column_header_reads_item_not_repo"
        status: pass
    human_judgment: false
  - id: D6
    description: "Real Hacker News/npm/PyPI/changelog rows render correctly on the deployed Coolify dashboard against live data"
    verification: []
    human_judgment: true
    rationale: "Local dev/test Postgres cluster has 0 real non-GitHub rows (deploy-time-only, per Phase 3 deferred UAT); this plan's non-GitHub coverage is verified via synthetic rows inserted into the ephemeral pytest-postgresql test cluster, not a real HN/npm/PyPI/changelog row. Live verification is already tracked as a deferred UAT item in STATE.md (Phase 3 SC1)."

# Metrics
duration: 20min
completed: 2026-08-26
status: complete
---

# Quick Task 260825-twr: Fix Dashboard Mislabeling Non-GitHub Items Summary

**Source-branched dashboard link labels (HN/npm/PyPI/changelog/GitHub) with a suppressed GitHub-only second link and a renamed "Item" header, verified via synthetic non-GitHub rows in the ephemeral test cluster.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-08-26T01:23:00Z
- **Completed:** 2026-08-26T01:43:36Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `_QUERY_RANKED_SQL` now selects `entities.source` so the template can branch per row
- `table.html`'s primary action link shows a source-honest label ("View on HN" / "View on npm" / "View on PyPI" / "View changelog" / "View on GitHub"), with href unchanged (`row['url']`) for every source
- The GitHub-specific second link (Docs/Repo fallback) now only renders for `source == 'github'` rows, eliminating the bogus second link on non-GitHub rows
- Name-column sort header renamed from "Repo" to "Item"
- Added 3 new tests covering HN labeling + link suppression, npm/PyPI/changelog labeling, and the "Item" header; all pre-existing tests (including the GitHub docs/repo fallback test) pass unchanged

## Task Commits

Each task was committed atomically:

1. **Task 1: Select source in query + branch link label and second-link visibility in template** - `a68c971` (fix)
2. **Task 2: Add tests for non-GitHub link labeling, suppressed second link, and Item header** - `05467df` (test)

**Plan metadata:** committed separately by the orchestrator (docs commit, per quick-task convention).

## Files Created/Modified
- `techtrend/server/queries.py` - Added `entities.source` to `_QUERY_RANKED_SQL`'s SELECT list with an inline comment explaining why (template branching)
- `techtrend/web/templates/partials/table.html` - Renamed name-column header text to "Item"; branched the primary action-link label on `row['source']` via if/elif/else; wrapped the GitHub Docs/Repo second link in `{% if row['source'] == 'github' %}`
- `tests/test_dashboard.py` - Added `test_hn_row_shows_view_on_hn_and_no_github_or_repo_docs_link`, `test_name_column_header_reads_item_not_repo`, and `test_non_github_sources_show_source_appropriate_primary_label`

## Decisions Made
- Second link gates on `row['source'] == 'github'` (not `docs_url` presence) — this was locked in the plan's `<key_decisions>` and is required to keep `test_row_links_source_before_docs_with_honest_label`'s undocumented-GitHub-repo case (which still expects a `Repo`-labeled fallback link) passing unchanged.
- Primary link's `href` stays `row['url']` for every source; only the visible label text branches — no URL-construction logic added per source.
- Used a Jinja if/elif/else chain (matching the file's existing style, e.g. the `sort == 'name'` conditional glyph blocks) rather than a dict lookup, for readability consistency with the rest of `table.html`.

## Deviations from Plan

None - plan executed exactly as written. Both design decisions in `<key_decisions>` were honored: the second link gates on `source == 'github'`, and the primary link's href is unchanged across all sources.

## Issues Encountered
- The local dev shell's `pytest` invocation initially failed with `ModuleNotFoundError: No module named 'pytest_postgresql'` because the venv wasn't on PATH by default, then failed a second time with `ExecutableMissingException: Could not find pg_config executable` because PostgreSQL's `bin/` directory (`C:\Program Files\PostgreSQL\17\bin`) wasn't on PATH for the Bash tool's shell. Resolved by explicitly invoking `.venv/Scripts/python.exe` and prepending the PostgreSQL bin directory to `PATH` for the test-run commands only (no permanent environment change). Not a plan deviation — purely a local test-invocation environment detail.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Dashboard now correctly labels every source type the collectors registry supports (github/hn/npm/pypi/changelog); no further presentation-layer work is blocking Phase 3's multi-source rollout.
- Live verification against real non-GitHub rows on the deployed Coolify dashboard remains a deferred UAT item (already tracked in STATE.md under Phase 3 SC1 — "Live multi-day, multi-source ranking") — this quick task does not resolve that deferred item, it only ensures the rendering will be correct once real rows exist.

---
*Phase: quick-260825-twr*
*Completed: 2026-08-26*

## Self-Check: PASSED

All claimed artifacts and commits verified present:
- `techtrend/server/queries.py` - FOUND
- `techtrend/web/templates/partials/table.html` - FOUND
- `tests/test_dashboard.py` - FOUND
- `.planning/quick/260825-twr-fix-dashboard-mislabeling-non-github-ite/260825-twr-SUMMARY.md` - FOUND
- Commit `a68c971` - FOUND
- Commit `05467df` - FOUND
