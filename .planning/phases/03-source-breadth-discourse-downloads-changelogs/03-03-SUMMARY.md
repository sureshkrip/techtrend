---
phase: 03-source-breadth-discourse-downloads-changelogs
plan: 03
subsystem: ui
tags: [dashboard, jinja2, htmx, postgres, documentation]

# Dependency graph
requires:
  - phase: 03-source-breadth-discourse-downloads-changelogs
    plan: 01
    provides: "normalize.py::PRIMARY_METRIC + score.py per-source metric_name (non-GitHub entities can now score eligible=1)"
  - phase: 03-source-breadth-discourse-downloads-changelogs
    plan: 02
    provides: "curated config sections + unauthenticated public HTTP client substrate"
provides:
  - "table.html header labels generalized to source-agnostic wording ('Gained'/'Total'), URL sort-param keys unchanged"
  - "queries.py stars_total alias documented as backing the source-agnostic Total column"
  - "tests/test_dashboard.py: _insert_entity accepts an optional source param; new tests prove label generalization and non-GitHub em-dash rendering"
  - "ROADMAP.md Phase 3 SC2/SC3 dated supersession notes (D3-2 deferral, D3-5 revision)"
  - "REQUIREMENTS.md cross-referenced descope note for the v2 cross-source entity resolution deferral"
affects: [03-04, 03-05, 03-06]

# Tech tracking
tech-stack:
  added: []
  patterns: ["dashboard header text kept source-agnostic while URL sort-param keys stay a stable contract"]

key-files:
  created: []
  modified:
    - techtrend/server/queries.py
    - techtrend/web/templates/partials/table.html
    - tests/test_dashboard.py
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Only visible header text was generalized ('Stars gained' -> 'Gained', 'Stars' -> 'Total'); SORT_KEYS dict keys and hx-get sort= URL params were left untouched as the stable contract Wave-2 collectors depend on"
  - "The stars_total SQL subquery's metric_name='stars' binding was NOT generalized (per RESEARCH Open Question 2) -- a non-GitHub row legitimately has no stars snapshot and degrades to an em-dash, which is the accepted v1 tradeoff"
  - "ROADMAP/REQUIREMENTS supersession notes mirror the existing SQLite->Postgres and Phase-4-rescope strike-through + dated-note style exactly, per the honest-supersession convention"

requirements-completed: [COLL-03, COLL-04, COLL-05]

coverage:
  - id: D1
    description: "Dashboard header labels read source-agnostically ('Gained'/'Total'); sort links and glyphs still function against unchanged SORT_KEYS/URL contract"
    requirement: COLL-03
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_column_headers_use_source_agnostic_labels_not_stars"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard.py::test_sort_stars_reorders_and_unrecognized_sort_falls_back_to_velocity"
        status: pass
    human_judgment: false
  - id: D2
    description: "A non-GitHub row (source='changelog', no 'stars' snapshot) renders its total cell as an em-dash without raising"
    requirement: COLL-05
    verification:
      - kind: unit
        ref: "tests/test_dashboard.py::test_non_github_row_with_no_stars_snapshot_renders_em_dash_total"
        status: pass
    human_judgment: false
  - id: D3
    description: "ROADMAP Phase 3 SC2/SC3 carry dated deferral/revision notes naming the three D3-5 deviations; REQUIREMENTS carries a cross-referenced descope note; no silent edits, no renumbering"
    requirement: COLL-04
    verification:
      - kind: unit
        ref: "python -c verify script from 03-03-PLAN.md Task 3 <verify> block"
        status: pass
    human_judgment: false

duration: 17min
completed: 2026-08-22
status: complete
---

# Phase 3 Plan 03: Dashboard Label Generalization + Honest Supersession Notes Summary

**Generalized the GitHub-star-specific dashboard column labels ("Stars"/"Stars gained") to source-agnostic wording ("Total"/"Gained") while preserving the `?sort=stars`/`?sort=gained` URL contract, and recorded the D3-2 cross-source dedup descope and D3-5 SC3 revision in ROADMAP/REQUIREMENTS using the project's existing honest-supersession style.**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-08-22T22:03:24Z
- **Completed:** 2026-08-22T22:20:14Z
- **Tasks:** 3 completed
- **Files modified:** 5

## Accomplishments
- `table.html`: header link text changed from "Stars gained" -> "Gained" and "Stars" -> "Total"; `hx-get="/?sort=gained..."`/`hx-get="/?sort=stars..."` hrefs and the `sort == 'gained'`/`sort == 'stars'` active-glyph conditionals left byte-identical
- `queries.py`: added a comment documenting that the `stars_total` SQL alias now backs the source-agnostic "Total" column, and that it correctly returns NULL (rendered as an em-dash) for a non-GitHub entity — `SORT_KEYS` dict keys (`velocity`/`stars`/`gained`/`name`) were not renamed
- `tests/test_dashboard.py`: `_insert_entity` gained an optional `source` parameter (defaults to `"github"`, zero behavior change for existing 19 tests); two new tests added — one asserting "Stars gained" no longer appears anywhere in the rendered header and that the header cells read "Gained"/"Total", one asserting a `source='changelog'` entity with no `'stars'` snapshot renders its total cell as `—` without raising
- `ROADMAP.md` Phase 3: SC2 struck through with a dated 2026-08-22 (D3-2) deferral note (cross-source dedup descoped to v2, separate rows per source for v1); SC3 struck through with a dated 2026-08-22 (D3-5) revision note naming the three actual deviations taken across 03-01/03-02/03-03 (scorer metric-name parameterization, dashboard label generalization, unauthenticated HTTP client) and stating the gate/enricher remain untouched
- `REQUIREMENTS.md`: added a dated descope note under the Collection section header cross-referencing D3-2 and clarifying it does not affect COLL-09 (within-source resolution, already satisfied); extended the v2 "Cross-source entity resolution" bullet to explicitly cover the Phase 3 SC2 descope

## Task Commits

Each task was committed atomically:

1. **Task 1: Generalize the dashboard momentum labels to source-agnostic wording** - `2899dbe` (feat)
2. **Task 2: Assert generalized labels + non-GitHub row rendering in the dashboard test** - `b8e3f23` (test)
3. **Task 3: Record the D3-2 dedup descope and D3-5 SC3 revision honestly in ROADMAP + REQUIREMENTS** - `59b7b64` (docs)

## Files Created/Modified
- `techtrend/server/queries.py` - documented the `stars_total` alias's new source-agnostic role; `SORT_KEYS` unchanged
- `techtrend/web/templates/partials/table.html` - "Stars gained"/"Stars" header text generalized to "Gained"/"Total"
- `tests/test_dashboard.py` - `_insert_entity(source=...)` param + 2 new tests (21 tests total, up from 19)
- `.planning/ROADMAP.md` - Phase 3 SC2/SC3 dated supersession notes
- `.planning/REQUIREMENTS.md` - cross-referenced descope note near Collection section + v2 list

## Decisions Made
- Kept the deviation surface exactly to "generalize visible labels" as D3-5 locked — did not touch the `stars_total` subquery's `metric_name = 'stars'` binding, matching RESEARCH's explicit "leave as-is, degrades gracefully" guidance
- Used today's date (2026-08-22) for both ROADMAP and REQUIREMENTS supersession notes, matching the SQLite->Postgres and Phase-4-rescope precedent style (strike-through + bold dated note, never a silent edit)
- Left Plans-list checkboxes and phase status in ROADMAP.md untouched — this plan's docs deliverable is content-only (SC2/SC3 text + REQUIREMENTS note), not bookkeeping

## Deviations from Plan

None - plan executed exactly as written. All three tasks matched their `<action>`/`<verify>`/`<done>` blocks; no Rule 1-4 fixes were needed.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The full D3-5 deviation surface is now closed across all three Wave-1 plans: scorer metric parameterization (03-01), config/HTTP substrate (03-02), and dashboard label generalization + honest documentation (03-03, this plan).
- Wave-2 collectors (HN, npm/PyPI, changelog — 03-04 through 03-06) can proceed without further scorer, config, HTTP-client, or dashboard changes; a non-GitHub row already renders correctly end-to-end once those collectors write `snapshots`/`scores` rows.
- `pytest tests/test_dashboard.py -x` passes (21/21). Full project test suite (`pytest -q`, all files, Postgres-backed) exits 0 with no regressions outside the touched files.

---
*Phase: 03-source-breadth-discourse-downloads-changelogs*
*Completed: 2026-08-22*

## Self-Check: PASSED

All modified files confirmed present on disk; all three task commit hashes (2899dbe, b8e3f23, 59b7b64) confirmed present in `git log --oneline --all`.
