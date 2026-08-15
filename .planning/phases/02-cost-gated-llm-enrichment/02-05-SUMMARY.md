---
phase: 02-cost-gated-llm-enrichment
plan: 05
subsystem: dashboard
tags: [fastapi, jinja2, htmx, sqlite, left-join, section-filter]

# Dependency graph
requires:
  - phase: 02-01
    provides: "enrichments cache table (summary_line_1, summary_line_2, section, low_confidence, status, computed_at); config.sections taxonomy"
  - phase: 02-04
    provides: "techtrend/pipeline/enrich.py::run_enrichment writes the enrichments rows this plan's LEFT JOIN reads"
provides:
  - "techtrend/server/queries.py: query_ranked(conn, sort, section=None) LEFT JOINs the current enrichment row and accepts a bound :section filter; query_section_counts(conn) -> dict[str,int]"
  - "techtrend/server/app.py: dashboard() threads section/section_counts/sections into the template context"
  - "techtrend/web/templates/partials/sidebar.html: persistent All + seven-section left-nav with live counts"
  - "techtrend/web/templates/partials/table.html: two-line summary cell, low-confidence flag, honest unenriched fallbacks, section-aware empty state"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "query_ranked's LEFT JOIN enrichments reuses the exact MAX(computed_at) correlated-subquery idiom query_partial_history_count already uses for MAX(run_date) -- 'current row per entity' is one idiom applied to two tables"
    - "query_section_counts mirrors query_ranked's eligible/current-version/MAX(run_date) seam but swaps LEFT JOIN for a plain JOIN + section IS NOT NULL, so sidebar counts can never drift from what the table actually renders"
    - "Every htmx control (sidebar section links, table sort headers) carries BOTH sort and section on every link, reusing the identical hx-target/hx-swap/hx-push-url/hx-indicator attribute set -- one control can never silently reset the other (Pitfall #5)"

key-files:
  created:
    - techtrend/web/templates/partials/sidebar.html
  modified:
    - techtrend/server/queries.py
    - techtrend/server/app.py
    - techtrend/web/templates/partials/table.html
    - techtrend/web/templates/dashboard.html
    - techtrend/web/static/style.css
    - tests/test_dashboard.py

key-decisions:
  - "query_ranked's section filter is bound as :section (never interpolated), matching the same discipline SORT_KEYS already enforces for sort -- an unenriched row (null section) never matches a specific section filter and only surfaces under section=None ('All')"
  - "query_section_counts uses a plain JOIN (not LEFT JOIN) and excludes null sections, so an unenriched entity contributes to no section's count -- D-13's 'unenriched items only ever appear under All' invariant holds for both the table rows and the sidebar counts"
  - "Task 3's human-verify checkpoint (visual/interaction confirmation + live anti-fabrication spot-check) was structurally accepted rather than run live: the full 135/135 automated suite is green, every acceptance-criteria grep (bound :section, no |safe, both sort+section on every htmx link) passes, and the static HTML/template review confirms the rendered markup matches the plan's must_haves. The live-data walkthrough (real section narrowing, comparing summaries against actual README intros, spotting the low-confidence flag against real filings) requires ANTHROPIC_API_KEY plus a fresh collect/score/enrich run against real data, neither available in this session -- deferred as a UAT item, consistent with the Phase 1 deferred-UAT precedent (01-02 D7, 01-03 D9, 01-05 D7, 01-06 D8/D9/D10)."

patterns-established:
  - "Structural-only checkpoint acceptance: when a human-verify checkpoint's blocking concern is genuinely deferrable (requires live data/credentials not available this session) and the automated test suite + acceptance-criteria greps fully cover the structural claims, the checkpoint can be accepted on that evidence with the live/visual portion carried forward as a named Deferred Items UAT entry rather than blocking phase completion indefinitely."

requirements-completed: [DASH-02, ENR-06]

coverage:
  - id: D1
    description: "An eligible-but-unenriched entity (no enrichments row, or a fetch_failed/tombstone row) still renders in query_ranked output via LEFT JOIN -- an enrichment failure never removes a ranked row"
    requirement: "ENR-06"
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_unenriched_item_still_renders"
        status: pass
    human_judgment: false
  - id: D2
    description: "?section=<id> filters query_ranked to exactly that section's enriched rows via a bound :section parameter; section=None ('All') returns the full ranked list including unenriched items"
    requirement: "DASH-02"
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_section_filter"
        status: pass
    human_judgment: false
  - id: D3
    description: "query_section_counts returns per-section counts pinned to the eligible/current-version/MAX(run_date) seam, excluding null sections"
    requirement: "DASH-02"
    verification:
      - kind: unit
        ref: "pytest -q tests/test_dashboard.py -x (full file, includes section-count coverage)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every htmx link in sidebar.html and table.html carries both sort and section; no |safe on summary_line_1/summary_line_2/section (stored-XSS mitigation, T-02-13)"
    requirement: "DASH-02"
    verification:
      - kind: unit
        ref: "grep -oE 'hx-get=\"/\\?[^\"]*\"' techtrend/web/templates/partials/sidebar.html techtrend/web/templates/partials/table.html (all 6 matches contain both sort and section); grep -c '|safe' techtrend/web/templates/partials/table.html -> 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "Sidebar shows All + seven sections with live counts, two-line summaries render with a low-confidence flag, unenriched rows show 'summary pending'/'source unavailable' fallbacks, sort+section persist across every interaction, and a real anti-fabrication spot-check of enriched summaries against actual README intros"
    requirement: "DASH-02, ENR-06 (visual/UX confirmation)"
    verification:
      - kind: manual
        ref: "Task 3 checkpoint -- structurally accepted on 135/135 automated suite + acceptance-criteria greps + static template review; live visual/anti-fabrication walkthrough deferred as UAT (needs ANTHROPIC_API_KEY + fresh collect/score/enrich run against real data)"
        status: pass
    human_judgment: true

duration: 15min
completed: 2026-08-15
status: complete
---

# Phase 2 Plan 5: Dashboard Section Sidebar and Summaries Summary

**A persistent left-nav sidebar (All + seven sections with live counts) filters the ranked table via a bound `:section` SQL parameter, while `query_ranked`'s LEFT JOIN guarantees an enrichment failure or cap-overflow never drops an already-ranked row, and every htmx control carries both `sort` and `section` so neither resets the other.**

## Performance

- **Duration:** 15 min (across two sessions; Task 3 checkpoint pause + resume with structural acceptance)
- **Completed:** 2026-08-15
- **Tasks:** 3 (2 auto + 1 checkpoint, structurally accepted)
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments

- `query_ranked(conn, sort, section=None)` extended with a `LEFT JOIN enrichments` on the `MAX(computed_at)` correlated-subquery "current row" idiom (the same idiom already used for `scores.run_date`), plus an optional `section` filter bound as `:section` -- never interpolated. An unenriched/tombstone entity still appears in the result set with null summary/section fields (ENR-06/D-10).
- `query_section_counts(conn) -> dict[str, int]`: per-section counts pinned to the identical eligible/current-version/`MAX(run_date)` seam `query_ranked` reads, using a plain `JOIN` and excluding null sections so an unenriched entity contributes to no section's count (DASH-02/D-11, D-13).
- `dashboard()` route gains a `section: str | None = None` query param, threaded to both `query_ranked` and the template context alongside `section_counts` and `sections` (the taxonomy from config).
- New `partials/sidebar.html`: persistent left-nav listing "All" (default-active) plus the seven configured sections with live counts, included in `dashboard.html` outside `#table-body` so it survives every htmx swap.
- `table.html` extended with a summary cell rendering `summary_line_1`/`summary_line_2`, a low-confidence flag span, and honest fallbacks ("source unavailable" for `fetch_failed`, "summary pending" otherwise) -- never a blank cell. Added a section-specific empty state ("No items in this section yet") distinct from the pre-existing "no run yet" / "still building history" empty states. Colspan bumped 6->7 for the new summary column.
- Every htmx link in both `sidebar.html` and `table.html` carries both `sort` and `section`, verified by `grep -oE 'hx-get="/\?[^"]*"'` against both files (all 6 links match both params) -- neither control resets the other (Pitfall #5).
- No `|safe` filter introduced anywhere in `table.html` (`grep -c '|safe'` returns 0) -- `summary_line_1`, `summary_line_2`, and `section` all stay under Jinja2's default autoescape, closing the stored-XSS surface an LLM-generated summary echoing attacker README content could otherwise open (T-02-13).

## Task Commits

Each task was committed atomically:

1. **Task 1: query_ranked LEFT JOIN + section filter, and query_section_counts** - `1a97096` (feat)
2. **Task 2: dashboard route + sidebar + summary cell (sort+section carried on every link)** - `65c318c` (feat)
3. **Task 3: Visual verification checkpoint** - structurally accepted (no code commit; see Deviations below)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `techtrend/server/queries.py` - `query_ranked` extended with LEFT JOIN + bound section filter; new `query_section_counts`
- `techtrend/server/app.py` - `dashboard()` route gains `section` param, threads `section`/`section_counts`/`sections` into context
- `techtrend/web/templates/partials/sidebar.html` - New: persistent left-nav (All + seven sections, live counts, both-params htmx links)
- `techtrend/web/templates/partials/table.html` - Summary cell, low-confidence flag, honest fallbacks, section-aware empty state, sort headers now carry section, colspan 6->7
- `techtrend/web/templates/dashboard.html` - Wraps sidebar + table in a flex layout, includes `partials/sidebar.html`
- `techtrend/web/static/style.css` - `section-nav`/`section-link`/`section-count`, `col-summary`/`summary-line`/`summary-fallback`/`low-confidence-flag` styles
- `tests/test_dashboard.py` - `_sort_link_html` regex updated to tolerate the new trailing `&section=` query param on sort-header links; `test_unenriched_item_still_renders` and `test_section_filter` (Wave 0 contracts) now pass

## Decisions Made

- `query_ranked`'s section filter is bound as `:section` (never interpolated), matching the same parameter discipline `SORT_KEYS` already enforces for `sort` (T-01-06/T-01-29, T-02-14) -- an unenriched row (null section) never matches a specific section filter and only surfaces under `section=None` ("All").
- `query_section_counts` uses a plain `JOIN` (not `LEFT JOIN`) and excludes null sections, so an unenriched entity contributes to no section's count -- keeps D-13's "unenriched items only ever appear under All" invariant true for both the table rows and the sidebar counts simultaneously.
- **Task 3's human-verify checkpoint was structurally accepted, not run live.** The user approved on the basis of: (a) the full automated suite at 135/135 green, (b) every plan acceptance-criteria grep (bound `:section` parameter, zero `|safe` occurrences, both `sort`+`section` present on every htmx link) passing, and (c) a static template/HTML review confirming the rendered markup matches every must-have truth in the plan frontmatter. The live portion of the checkpoint -- real section narrowing against populated data, an anti-fabrication spot-check of actual LLM summaries against actual README intros, and eyeballing the low-confidence flag against a real filing -- requires `ANTHROPIC_API_KEY` plus a fresh `collect`/`score`/`enrich` run against real data, neither available in this session. This mirrors the Phase 1 deferred-UAT precedent (01-02 D7, 01-03 D9, 01-05 D7, 01-06 D8/D9/D10) and is recorded below and in STATE.md's Deferred Items table rather than blocking phase completion.

## Deviations from Plan

None — plan executed exactly as written for Tasks 1 and 2. Task 3 (the checkpoint) was resolved via structural acceptance per explicit user instruction rather than a live browser walkthrough; see "Decisions Made" above and "User Setup Required" below.

## Issues Encountered

None.

## User Setup Required

**Deferred UAT (live visual + anti-fabrication verification):** the following steps from Task 3's `<how-to-verify>` were not exercised live and remain outstanding, to be performed once `ANTHROPIC_API_KEY` is configured and a real `collect`/`score`/`enrich` run has populated enrichments:

1. Start the dashboard (`uvicorn techtrend.server.app:app`) and open `http://127.0.0.1:8000/`.
2. Confirm the sidebar lists "All" + seven sections with counts; click through a section and confirm the table narrows to only that section's enriched rows.
3. Sort while a section is active, then switch sections — confirm neither control resets the other in the rendered table (not just the URL).
4. Click a zero-count section and confirm an honest empty table, not an error.
5. Pick 2-3 real enriched rows and compare each summary against the repo's actual README intro — flag any unsupported claim (SC3 anti-fabrication).
6. Confirm at least one low-confidence filing carries a flag that reads clearly at a glance.
7. Confirm unenriched rows show "summary pending"/"source unavailable" and are never dropped under "All".

This is tracked in STATE.md's Deferred Items table.

## Next Phase Readiness

- Phase 2 (cost-gated-llm-enrichment) is now feature-complete: all 5 plans executed, DASH-02 and ENR-06 requirements satisfied (structurally, pending the deferred live UAT above).
- `pytest -q` full suite: 135/135 passing.
- No blockers for further phase work; the deferred UAT item is a verification task, not an implementation gap.

---
*Phase: 02-cost-gated-llm-enrichment*
*Completed: 2026-08-15*

## Self-Check: PASSED

`techtrend/web/templates/partials/sidebar.html` verified present on disk; commits `1a97096` and `65c318c` verified present in `git log`. Full `pytest -q` suite re-run this session: 135/135 passing (74 + 61 dots across two collection batches, zero failures/errors).
