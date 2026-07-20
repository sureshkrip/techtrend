---
phase: 01-foundation-first-signal-github-scored-and-visible
plan: 06
subsystem: dashboard
tags: [fastapi, jinja2, htmx, sqlite, health-strip, sort]

# Dependency graph
requires:
  - phase: 01-04
    provides: "scores table (wilson_lower_bound, eligible, score_version, window_days) via rescore_all"
  - phase: 01-05
    provides: "run_manifest rows via record_stage, entities.docs_url/docs_url_kind"
provides:
  - "GET / dense sortable dashboard table (rank, name, velocity, stars gained, stars total, source link, docs link)"
  - "Allow-listed sort (SORT_KEYS) with deterministic entities.id ASC tiebreak, htmx GET partial re-render"
  - "Persistent three-tier escalating health strip over run_manifest (normal/stale/critical)"
  - "Honest docs-vs-repo link labeling (D-15) and partial-history footer note (D-08a)"
affects: [phase-2-section-filters, phase-4-missed-run-indicator]

tech-stack:
  added: []
  patterns:
    - "SORT_KEYS allow-dict: sort param never reaches SQL as raw text, unrecognized value falls back to velocity"
    - "query_ranked returns (rows, applied_sort) so the template renders the active-sort glyph against reality, not the request"
    - "Ranked query pinned to MAX(run_date) per score_version, matching rescore_all's delete-then-insert write pattern"
    - "Header row lives inside the swapped table partial so the sort glyph regenerates atomically with the rows"
    - "health_status() escalation order: never-completed > failed/zero-items-vs-trailing-average > stale > normal"

key-files:
  created:
    - techtrend/server/health.py
    - techtrend/web/templates/partials/health_strip.html
    - tests/test_dashboard.py
  modified:
    - techtrend/server/app.py
    - techtrend/server/queries.py
    - techtrend/web/templates/partials/table.html
    - techtrend/web/templates/dashboard.html
    - techtrend/web/static/style.css
    - tests/test_health.py
    - tests/test_skeleton.py

key-decisions:
  - "Pinned query_ranked/query_partial_history_count to MAX(run_date) per score_version -- scores carries PRIMARY KEY (entity_id, run_date, score_version), and an unpinned join would render one row per run_date for the same entity"
  - "Fixed a real copy bug: _stale_message/_failure_message appended a literal ' ago.' on top of relative_time(), which already returns a full phrase ('1 day ago'), producing 'ago ago' -- removed the redundant literal"
  - "dashboard.html no longer renders its own <thead>; table.html's header row lives inside #table-body so it regenerates atomically with the rows on every htmx swap (E3 mitigation, carried from the in-flight work)"
  - "Added a client-side htmx:responseError/htmx:sendError listener so a failed sort GET is visibly surfaced instead of htmx's default silent no-op (UI-SPEC E3 error backstop)"
  - "health_strip.html is included unconditionally in dashboard.html but renders nothing when health is None (total DB read failure) -- the db_error copy already communicates the outage without a raw traceback in that case"

patterns-established:
  - "Dashboard route tests seed entities/scores/snapshots directly against a real temp-file SQLite connection, then repoint techtrend.db.connection.DEFAULT_DB_PATH via monkeypatch before building a fastapi.testclient.TestClient (mirrors tests/test_skeleton.py)"

requirements-completed: [DASH-01, DASH-03, DASH-04, DASH-05, DASH-06, HEALTH-02]

coverage:
  - id: D1
    description: "Dense sortable table renders real scored entities (rank/name/velocity/stars-gained/stars-total/source/docs), ordered by wilson_lower_bound descending with entities.id ASC tiebreak, stable across repeated identical requests"
    requirement: "DASH-01"
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_ranked_rows_render_in_velocity_descending_order"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard.py::test_equal_bounds_break_tie_by_entity_id_ascending_and_are_stable"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard.py::test_zero_eligible_entities_renders_empty_state"
        status: pass
    human_judgment: false
  - id: D2
    description: "Allow-listed sort (velocity/stars/gained/name), unrecognized sort falls back to velocity, htmx HX-Request returns partial-only, active-sort glyph reflects the sort actually applied, velocity displays 4 decimals while sorting on the unrounded value"
    requirement: "DASH-03"
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_sort_stars_reorders_and_unrecognized_sort_falls_back_to_velocity"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard.py::test_hx_request_returns_only_the_table_partial"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard.py::test_active_sort_glyph_reflects_the_sort_actually_applied"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard.py::test_velocity_renders_four_decimals_while_sorting_on_unrounded_value"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every row links to GitHub source and docs/repo, source precedes docs in DOM order, docs label honestly degrades to 'Repo' when docs_url_kind is the bare-repo fallback (D-15)"
    requirement: "DASH-04"
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_row_links_source_before_docs_with_honest_label"
        status: pass
    human_judgment: false
  - id: D4
    description: "Partial-history footer note (singular/plural) for entities excluded by window_days below the configured window (D-08a)"
    requirement: "DASH-01"
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_partial_history_footer_singular_for_one_excluded_entity"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard.py::test_partial_history_footer_plural_for_multiple_excluded_entities"
        status: pass
    human_judgment: false
  - id: D5
    description: "Ranked query filters to the current score_version and eligible=1, and is pinned to the single latest run_date per score_version so an entity with scores rows across multiple run_dates renders exactly once (regression fix)"
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_ineligible_and_stale_score_version_rows_are_excluded"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard.py::test_entity_with_scores_across_two_run_dates_renders_exactly_once"
        status: pass
    human_judgment: false
  - id: D6
    description: "Dashboard performs SELECT statements only and never mutates the database on any request (D-17)"
    requirement: "DASH-01"
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_dashboard_never_writes_to_the_database"
        status: pass
      - kind: unit
        ref: "tests/test_skeleton.py::test_dashboard_never_writes"
        status: pass
    human_judgment: false
  - id: D7
    description: "Persistent three-tier health strip (normal/stale/critical) over run_manifest with D-16's exact escalation order: never-completed (distinct copy) > collector failed/zero-items-vs-non-trivial-trailing-average > stale (>36h, inclusive boundary) > normal; error_detail truncated to 120 chars before reaching the template"
    requirement: "HEALTH-02"
    verification:
      - kind: unit
        ref: "tests/test_health.py::test_recent_success_yields_normal_tier_with_relative_time"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_stale_run_yields_stale_tier_and_copy"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_staleness_boundary_is_inclusive_on_the_healthy_side"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_staleness_boundary_one_minute_past_is_stale"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_failed_collector_yields_critical_with_failure_copy"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_never_completed_uses_distinct_copy"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_zero_items_against_non_trivial_trailing_average_is_critical"
        status: pass
      - kind: unit
        ref: "tests/test_health.py::test_zero_items_against_trailing_average_of_zero_is_not_critical"
        status: pass
      - kind: integration
        ref: "tests/test_health.py::test_error_detail_truncated_in_rendered_health_strip"
        status: pass
      - kind: integration
        ref: "tests/test_health.py::test_health_strip_renders_for_normal_tier"
        status: pass
      - kind: integration
        ref: "tests/test_health.py::test_health_strip_renders_for_critical_tier_on_empty_run_manifest"
        status: pass
    human_judgment: false
  - id: D8
    description: "E3 sort-header error surfacing: a failed htmx sort GET (5xx/network) must not silently leave stale rows under a moved glyph"
    verification: []
    human_judgment: true
    rationale: "Implemented as a client-side htmx:responseError/htmx:sendError listener in dashboard.html -- pure browser JS with no server-observable effect, not exercisable from fastapi.testclient. Flagged as an unresolved UI-SPEC backstop, not a held-out automated test. Needs a real browser (e.g. dev-tools network throttling to a 500/offline) to confirm the swap actually fires."
  - id: D9
    description: "Visual density/legibility at real row counts, real sort-click interaction with no full-page reload, and live-credential GitHub ingest/backfill/score behavior"
    verification: []
    human_judgment: true
    rationale: "Task 3 (checkpoint:human-verify) is explicitly reserved by the user for personal verification per the plan and the resuming instructions. GITHUB_TOKEN is not configured in this environment, so live-credential behavior (ETag 304s, backfill 403 degradation) cannot be exercised by this executor. Visual scan-density judgment is inherently a human call. See the numbered checklist in the final report."
  - id: D10
    description: "DB-unreadable graceful degradation renders the Copywriting Contract's 'couldn't read the database' copy instead of a raw traceback"
    verification: []
    human_judgment: true
    rationale: "Manually smoke-tested during this session (an uninitialized/missing-table DB produced the correct copy, no traceback -- see report), but no automated pytest assertion exists for this path and the checkpoint's own step 9 explicitly asks the human to repeat it against a renamed real techtrend.db. Kept as a UI-SPEC-flagged backstop pending that manual pass."

duration: unspecified (resumed mid-Task-1 from a prior executor's stream-stall crash; not measured from a single start point)
completed: 2026-07-19
status: complete
---

# Phase 1 Plan 06: Dashboard Table, Honest Links, and Escalating Health Strip Summary

**Dense sortable FastAPI/Jinja2/htmx dashboard over `entities`/`scores`/`run_manifest`, with allow-listed sort, honest docs-vs-repo link labeling, a persistent three-tier health strip, and a run_date-dedup regression fix in the ranked query.**

## Performance

- **Duration:** Not precisely measured -- this executor resumed a session that a prior executor left mid-Task-1 after an API stream stall, with substantial uncommitted work already in the tree.
- **Completed:** 2026-07-19
- **Tasks:** 2 of 3 complete and committed (Task 3 is a checkpoint reserved for the user)
- **Files modified:** 9 (2 new, 7 modified) across the three commits below

## IMPORTANT: Task 3 is PENDING HUMAN VERIFICATION

**Do not treat this plan, or Phase 1, as done.** Tasks 1 and 2 are complete, tested, and committed. Task 3 (`checkpoint:human-verify`, gate=blocking) has **not** been run — it requires a real `GITHUB_TOKEN`, a real browser, and a human legibility/density judgment, none of which this executor can supply (no `GITHUB_TOKEN` is configured in this environment, and visual/interaction judgment is explicitly the user's call per the plan and the resuming instructions). STATE.md and ROADMAP.md have deliberately **not** been advanced past this plan — see "State Updates Deliberately Skipped" below. The numbered verification checklist is in the final report to the user, not duplicated here.

## Accomplishments

- Fixed the broken-suite root cause: `app.py` never unpacked `query_ranked()`'s `(rows, applied_sort)` tuple after `queries.py` was changed to return it, causing a Jinja2 `UndefinedError` on every dashboard render (4 failing tests). Now unpacks correctly and also wires `query_partial_history_count` and `health_status` into the route context.
- Fixed a real duplicate-row bug: `scores` carries `PRIMARY KEY (entity_id, run_date, score_version)`, and the ranked query's join filtered only on `score_version`/`eligible` with no `run_date` constraint — an entity with rows at multiple run_dates for the same score_version would have rendered once per run_date. Pinned both `query_ranked` and `query_partial_history_count` to `MAX(run_date)` per score_version, verified against `pipeline/score.py::rescore_all`'s actual delete-then-insert write pattern, with a dedicated regression test.
- Completed the dense sortable table (`partials/table.html`), the health strip (`server/health.py` + `partials/health_strip.html`), and the CSS (fixed column widths, ellipsis truncation, htmx loading-dim rule, health-tier colors) against the full UI-SPEC contract.
- Found and fixed a real copy bug in the in-flight `health.py`: the stale/failure message builders appended a literal `" ago."` on top of `relative_time()`'s output, which already includes "ago" — producing "...1 day ago ago." Caught by a new test, fixed to match the Copywriting Contract's actual rendered example.
- Added a client-side `htmx:responseError`/`htmx:sendError` listener (UI-SPEC E3 error backstop) so a failed sort GET surfaces visibly instead of htmx's default silent no-op.
- 41 new/updated tests: 13 in `tests/test_dashboard.py` (new), 11 new health-tier tests appended to `tests/test_health.py`, plus a `tests/test_skeleton.py` fixture update. Full suite: **96 passed, 0 skipped**. `ruff check .` clean.
- Manually smoke-tested via a real `uv run uvicorn` process: `GET /` returns 200 against both an uninitialized DB (correct "couldn't read the database" copy, no traceback) and a fixture-populated DB (correct empty-state + critical-health-strip rendering for a fresh, ineligible, never-collector-logged entity); `GET /?sort=stars` with `HX-Request: true` returns a partial with zero `<html` occurrences.

## Task Commits

Each task was committed atomically:

1. **Bugfix (pre-Task-1 recovery):** `6136c7d` — `fix(01-06): unpack query_ranked tuple in app.py, pin scores join to latest run_date`. Got the suite from 4-failing back to fully green before any new feature work, per the explicit "commit immediately once green" instruction.
2. **Task 1: Ranked query with allow-listed sorting and the dense table** — `3a88323` — `feat(01-06): dense sortable dashboard table with honest links and health-strip include`
3. **Task 2: Escalating health strip over run_manifest** — `901ffff` — `feat(01-06): escalating three-tier health strip over run_manifest`

No separate "docs: complete plan" metadata commit yet — deliberately deferred (see below).

## Files Created/Modified

- `techtrend/server/app.py` — unpacks `query_ranked`'s tuple, loads config, wires `health_status` and `query_partial_history_count` into the route context
- `techtrend/server/queries.py` — `query_ranked`/`query_partial_history_count` pinned to `MAX(run_date)` per score_version
- `techtrend/server/health.py` — three-tier `health_status()`, `HealthTier` (`StrEnum`), `relative_time()`; fixed the "ago ago" copy bug and two ruff findings
- `techtrend/web/templates/dashboard.html` — rewritten: single `<table><tbody id="table-body">` wrapping the table partial, unconditional health-strip include, `htmx:responseError`/`htmx:sendError` listener
- `techtrend/web/templates/partials/table.html` — dense table body (inherited mostly complete from the prior session; verified against every acceptance criterion)
- `techtrend/web/templates/partials/health_strip.html` — new; renders the tier-specific class and message
- `techtrend/web/static/style.css` — fixed column widths, ellipsis truncation, `#table-body.htmx-request` opacity rule, health-tier color classes
- `tests/test_dashboard.py` — new, 13 tests
- `tests/test_health.py` — 11 new tests appended
- `tests/test_skeleton.py` — `_seed_one_entity` now also seeds an eligible `scores` row (see Deviations)

## Decisions Made

- **Run_date pinning approach:** rather than assuming a bug existed, verified `pipeline/score.py::rescore_all` actually deletes all `CURRENT_SCORE_VERSION` rows before inserting the new run_date's rows in the same transaction — so under normal single-writer operation only one run_date is ever live per score_version. Pinning to `MAX(run_date)` matches that write pattern exactly and is defense-in-depth against any row set (test fixtures, a future change to `rescore_all`, a partial-write edge case) that leaves more than one run_date behind.
- **health_strip.html renders nothing when `health` is `None`:** only reachable when the whole DB read fails (caught by `app.py`'s `except sqlite3.Error`), in which case `db_error` already communicates the outage via `partials/table.html`'s db-error row. Judged acceptable rather than trying to compute a health tier off a broken connection.
- **`--fixture` ingest path does not write a `collect:github` run_manifest row** (confirmed by reading `ingest.py`) — so a fixture-only dashboard always shows the "never completed successfully" critical tier even though an entity exists. This is expected/pre-existing behavior of the offline dev path, not a defect introduced here; flagged for the human-verification checklist so it isn't mistaken for a bug.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `app.py` never unpacked `query_ranked`'s `(rows, applied_sort)` tuple**
- **Found during:** Recovery, before Task 1
- **Issue:** `queries.py` was changed (by a prior session) to return a `(rows, applied_sort)` tuple, but `app.py` still did `rows = query_ranked(...)` and passed the raw tuple to the template — every render raised `jinja2.exceptions.UndefinedError: 'list object' has no attribute 'wilson_lower_bound'`.
- **Fix:** Unpacked the tuple, used `applied_sort` for the `sort` context var (so the glyph renders against the sort that actually ran), and wired in `query_partial_history_count`/`health_status`.
- **Files modified:** `techtrend/server/app.py`
- **Verification:** `tests/test_skeleton.py`'s four dashboard tests, previously failing, now pass.
- **Committed in:** `6136c7d`

**2. [Rule 1 - Bug] Duplicate rows for an entity with scores across multiple run_dates**
- **Found during:** Recovery, before Task 1 (flagged explicitly in the resuming instructions)
- **Issue:** `_QUERY_RANKED_SQL` filtered only on `score_version`/`eligible`, with no `run_date` constraint, against a table keyed `(entity_id, run_date, score_version)`.
- **Fix:** Added `AND scores.run_date = (SELECT MAX(latest.run_date) FROM scores AS latest WHERE latest.score_version = :score_version)` to both `query_ranked` and `query_partial_history_count`.
- **Files modified:** `techtrend/server/queries.py`
- **Verification:** New regression test `test_entity_with_scores_across_two_run_dates_renders_exactly_once`.
- **Committed in:** `6136c7d`

**3. [Rule 1 - Bug] `tests/test_skeleton.py`'s `_seed_one_entity` fixture no longer matched the new eligible/score_version join semantics**
- **Found during:** Recovery, before Task 1
- **Issue:** With the score_version/eligible filter now active (carried, correctly, from 01-04), an entity with no `scores` row no longer renders at all — the fixture inserted only an `entities` row, so two skeleton tests (`test_dashboard_renders_seeded_repo`, `test_dashboard_row_links_to_source`) started failing on the empty-state branch instead of the populated branch.
- **Fix:** Updated the fixture to also insert an eligible `scores` row. This is the new, correct semantics — not a weakening of the test's assertions, which are unchanged.
- **Files modified:** `tests/test_skeleton.py`
- **Verification:** Both tests pass again; full suite green.
- **Committed in:** `6136c7d`

**4. [Rule 1 - Bug] Doubled "ago ago" in the stale/failure health-strip copy**
- **Found during:** Task 2, writing `test_stale_run_yields_stale_tier_and_copy`
- **Issue:** `_stale_message`/`_failure_message` (inherited in-flight) appended a literal `" ago."` after `{relative}`, but `relative_time()` already returns a full phrase including "ago" (e.g. "1 day ago") — producing "...last successful run was 1 day ago ago."
- **Fix:** Removed the redundant trailing `" ago."` from both message builders; the Copywriting Contract's own rendered example ("2 days ago") confirms `relative_time()`'s output is the whole phrase.
- **Files modified:** `techtrend/server/health.py`
- **Verification:** Test assertions for `"ago ago" not in result["message"]` in two tests.
- **Committed in:** `901ffff`

**5. [Rule 1 - Lint] Two ruff findings in the inherited `health.py`**
- **Found during:** Task 2, running `ruff check .`
- **Issue:** `class HealthTier(str, Enum)` flagged UP042 (prefer `enum.StrEnum`); two lines exceeded the 100-char limit (E501).
- **Fix:** Switched to `from enum import StrEnum` / `class HealthTier(StrEnum)`; wrapped the two long lines.
- **Files modified:** `techtrend/server/health.py`
- **Verification:** `ruff check .` exits clean.
- **Committed in:** `901ffff`

---

**Total deviations:** 5 auto-fixed (4 Rule 1 bugs, 1 Rule 1 lint cleanup). All were necessary for correctness (2 were the explicit recovery targets named in the resuming instructions); no scope creep beyond what the plan specified.

## Issues Encountered

- `.bashrc` on this machine emits a spurious `$'\377\376export': command not found` line on every Bash tool invocation (a UTF-16 BOM artifact in the profile). Harmless — every command still ran and produced correct output — but worth flagging since it appears in every command's stderr in this session's tool log.
- `uv run pytest --collect-only -q` and `uv run pytest -q`'s final summary line ("N passed in Xs") did not appear in captured output in this environment/terminal combination; per-file collection counts (`uv run pytest --collect-only -q`) were used instead to compute exact pass counts (96 total, all passing, confirmed no `F` in the dot output).
- A stray `techtrend.db` was created twice by this session's own `uv run uvicorn` smoke tests (once against an uninitialized DB, once after `python -m techtrend.ingest --fixture` + `python -m techtrend.score`). Both were deleted before finishing (`.gitignore` already covers `techtrend.db*`, so neither was ever a git-tracking risk) so the user's own Task 3 verification starts from a clean slate.

## User Setup Required

None from this plan directly, but Task 3's checklist (below, and in the final report) requires a real `GITHUB_TOKEN` in `.env` (see `.env.example`), which is not configured in this execution environment.

## State Updates Deliberately Skipped

Per the resuming instructions: **STATE.md and ROADMAP.md have not been advanced past this plan, and no phase-completion metadata commit has been made.** Specifically skipped:
- `state advance-plan` / `state record-session` marking 01-06 as the completed/current position
- `roadmap update-plan-progress` for phase 01
- `requirements mark-complete` for DASH-01/03/04/05/06/HEALTH-02
- The final `docs(01-06): complete ... plan` metadata commit bundling SUMMARY.md + STATE.md + ROADMAP.md + REQUIREMENTS.md

This SUMMARY.md itself is committed on its own (see final report for the commit hash) so the work is durable, but the plan/phase should only be marked complete after a human runs Task 3's checklist and confirms.

## Next Phase Readiness

- Tasks 1 and 2 are fully automated-verified and committed; the dashboard, sort, and health strip are functionally complete against every automatable UI-SPEC/must_haves item.
- **Blocker:** Task 3 (human verification) must run before this plan, and therefore Phase 1, can be considered done. See the numbered checklist in the final report to the user.
- E1 `overflow` (no pagination/virtualization) remains an explicit, unresolved planner assumption per the plan's `<planner_assumptions>` — not touched here, correctly not invented.

---
*Phase: 01-foundation-first-signal-github-scored-and-visible*
*Completed: 2026-07-19*

## Self-Check: PASSED

All key files (health.py, health_strip.html, test_dashboard.py, app.py, queries.py,
table.html, dashboard.html, style.css, test_health.py, test_skeleton.py, this SUMMARY)
confirmed present on disk. All three commit hashes (6136c7d, 3a88323, 901ffff) confirmed
present in `git log --oneline --all`.
