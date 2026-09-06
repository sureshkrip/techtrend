---
phase: quick-260906-n5d
plan: 01
subsystem: pipeline
tags: [enrichment, grounding, httpx, feedparser, hn, npm, pypi, changelog, github]

# Dependency graph
requires:
  - phase: 03-source-breadth
    provides: HN/npm/PyPI/changelog collectors registered and populating entities/scores
provides:
  - "Source-dispatching fetch_grounding() covering github/hn/npm/pypi/changelog"
  - "entities.source + entities.url threaded through select_candidates -> run_enrichment"
affects: [enrichment, dashboard-sections, section-classification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Source dispatcher pattern: fetch_grounding(source, ...) routes to a private per-source _fetch_*_grounding() strategy, never raises on unknown source"
    - "404-as-nothing-to-ground-on: npm/pypi grounding catches a 404 inside the fetch fn and returns None (tombstone), mirroring _get_readme_text's existing 404 handling"

key-files:
  created:
    - tests/fixtures/packages/npm_registry.json
    - tests/fixtures/packages/pypi_metadata.json
  modified:
    - techtrend/pipeline/grounding.py
    - techtrend/pipeline/enrich.py
    - tests/test_grounding.py
    - tests/test_enrich.py

key-decisions:
  - "GitHub path preserved byte-for-byte: extracted verbatim into _fetch_github_grounding, only the outer call signature changed"
  - "hn grounds on full_name (the real story title, already stored) with zero network fetch -- D-08 satisfied without a fetch"
  - "npm/pypi ground on first-party registry/JSON-API text via the unauthenticated public client, never the GitHub client"
  - "changelog re-parses the feed fresh via feedparser (grounding is explicitly a fresh fetch, not a collector) and grounds on the feed's own title + recent entry titles"
  - "select_candidates SQL only grew its SELECT column list (source, url) -- WHERE/ORDER BY/LIMIT untouched, selection stays source-agnostic"
  - "No new tunable, no schema migration, no LLM signature/prompt change"

patterns-established:
  - "Grounding strategies live as private _fetch_<source>_grounding() functions in grounding.py behind one public dispatcher"

requirements-completed: [ENR-04, ENR-05]

coverage:
  - id: D1
    description: "fetch_grounding dispatches on entities.source to five strategies (github/hn/npm/pypi/changelog); GitHub behavior preserved byte-for-byte; unknown source returns None without raising"
    requirement: "ENR-05"
    verification:
      - kind: unit
        ref: "tests/test_grounding.py (22 tests covering all five sources, 404 handling, empty-both-fields tombstone, unknown-source fallback)"
        status: pass
    human_judgment: false
  - id: D2
    description: "select_candidates selects entities.source + entities.url alongside full_name; selection WHERE/ORDER BY/LIMIT logic unchanged"
    requirement: "ENR-04"
    verification:
      - kind: unit
        ref: "tests/test_enrich.py::test_gate_reads_eligible_seam"
      - kind: other
        ref: "python -c import techtrend.pipeline.enrich as e; assert 'entities.source' in e._SELECT_CANDIDATES_SQL and 'entities.url' in e._SELECT_CANDIDATES_SQL"
        status: pass
    human_judgment: false
  - id: D3
    description: "run_enrichment threads (source, full_name, url) into a source-dispatching fetch_grounding_fn; all existing gates (eligible-set, hard cap, cache-hit skip, tombstone-on-empty, per-candidate isolation) preserved"
    requirement: "ENR-05"
    verification:
      - kind: unit
        ref: "tests/test_enrich.py::test_multi_source_orchestration_enriches_every_source"
      - kind: unit
        ref: "tests/test_enrich.py (19 tests total, cache-hit/fetch-failure/per-candidate-failure/cap/gate all pass)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live confirmation that HN/npm/PyPI/changelog rows actually get enriched against real Algolia/registry/RSS APIs on the deployed Coolify instance"
    verification: []
    human_judgment: true
    rationale: "Local dev DB is github-only (per project memory) and the test cluster uses synthetic rows + fixtures only -- a live multi-source enrichment run needs the deployed environment with real API access, matching the same deferred UAT pattern already used for Phase 3 SC1."

# Metrics
duration: 55min
completed: 2026-09-06
status: complete
---

# Quick Task 260906-n5d: Fix source-blind categorization Summary

**Made `grounding.py::fetch_grounding` source-dispatching (github/hn/npm/pypi/changelog) so Hacker News, npm, PyPI, and changelog items stop 404ing against the GitHub REST API and silently vanishing from enrichment — they now get a real summary + section, or an honest `fetch_failed` tombstone.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-09-06T (session start)
- **Completed:** 2026-09-06
- **Tasks:** 2
- **Files modified:** 6 (2 source, 2 test, 2 new fixtures)

## Accomplishments

- `grounding.py::fetch_grounding` now dispatches on `source`: GitHub keeps its exact pre-existing metadata+README behavior via `_fetch_github_grounding` (extracted verbatim); HN grounds on the already-stored story title with zero network fetch; npm/PyPI fetch first-party registry/JSON-API text via the unauthenticated public client (404 → tombstone, not an exception); changelog re-parses the feed fresh and grounds on its title + recent entry titles; an unrecognized source logs a warning and returns `None` rather than raising.
- `enrich.py::_SELECT_CANDIDATES_SQL` now selects `entities.source` + `entities.url` alongside `full_name` — the eligible-set WHERE clause, ORDER BY, and hard-cap LIMIT are byte-for-byte unchanged, so selection stays source-agnostic.
- `run_enrichment`'s production seam now builds both `build_client()` (authenticated, GitHub) and `build_public_client()` (unauthenticated, npm/PyPI) once per run and threads `(source, full_name, url)` into the dispatching `fetch_grounding_fn` — a zero-candidate run still needs no `GITHUB_TOKEN`.
- Added a multi-source end-to-end orchestration test that seeds one eligible entity per source (github/hn/npm/pypi/changelog) plus one entity whose grounding genuinely returns nothing, and proves all five real sources land a `status='complete'` row with a non-null `section` while the empty one gets an honest `status='fetch_failed'` tombstone with `content_hash IS NULL`.

## Task Commits

Each task was committed atomically (Task 1 followed its `tdd="true"` RED→GREEN discipline):

1. **Task 1 (RED): failing tests for the source dispatcher** — `7f23d51` (test)
2. **Task 1 (GREEN): grounding.py source-aware implementation** — `8cc1b9d` (feat)
3. **Task 2: thread source+url through enrich.py** — `6cfbd05` (fix)

**Plan pre-dispatch commit:** `8fb0521` (docs)

## Files Created/Modified

- `techtrend/pipeline/grounding.py` — added `_fetch_hn_grounding`, `_fetch_npm_grounding`, `_fetch_pypi_grounding`, `_fetch_changelog_grounding`, and the public `fetch_grounding(source, full_name, url, char_cap, *, github_client, public_client)` dispatcher; renamed the old body to `_fetch_github_grounding` (unchanged logic)
- `techtrend/pipeline/enrich.py` — `_SELECT_CANDIDATES_SQL` gained `entities.source`/`entities.url`; `run_enrichment` builds both HTTP clients and threads `(source, full_name, url)` into the grounding seam; candidate loop reads `source`/`url` and includes `source` in the per-candidate failure log line
- `tests/test_grounding.py` — updated GitHub tests to the new dispatcher signature; added hn/npm/pypi/changelog/unknown-source tests (22 tests total)
- `tests/test_enrich.py` — `_insert_entity` gained `source=`/`url=` params; the four existing fake-grounding fixtures updated to `(source, full_name, url)`; added `test_multi_source_orchestration_enriches_every_source`
- `tests/fixtures/packages/npm_registry.json` — new fixture, minimal packument with `description` + `readme`
- `tests/fixtures/packages/pypi_metadata.json` — new fixture, minimal object with `info.summary` + `info.description`

## Decisions Made

- GitHub grounding preserved byte-for-byte by extracting the pre-existing function body verbatim into `_fetch_github_grounding` — no behavior change, only the outer signature/dispatch layer is new.
- HN grounds on `full_name` (the real story title, per `hn.py::normalize`) with no network fetch at all — the title alone is genuine, already-stored text, satisfying D-08 without a fetch and without needing a scraping/readability layer (which CLAUDE.md's "What NOT to Use" explicitly excludes).
- npm/pypi grounding fetches are routed through `build_public_client()` (unauthenticated), never `build_client()` (GitHub-authenticated) — a separate retry-kwargs set (`_RETRY_KWARGS_PUBLIC`) keyed on `is_retryable_public` is used, matching the collectors' existing pattern.
- A 404 on the npm/pypi fetch is caught *inside* the grounding function and treated as "nothing to ground on" (returns `None` → tombstone), mirroring how `_get_readme_text` already handles a 404 README — rather than letting the exception propagate into the outer per-candidate try/except (which would still skip the candidate, but with a less honest log signal).
- changelog grounding is a fresh `feedparser.parse()` call, not a reuse of collector state — grounding is explicitly documented as "freshly fetched" text, and the collector's own fetch only returns a release *count*, not entry titles.
- `select_candidates`'s WHERE/ORDER BY/LIMIT logic was left completely untouched per the plan's locked decision — the bug was in the FETCH, not selection, so selection scope was never widened or narrowed.

## Deviations from Plan

None — plan executed exactly as written. Both tasks' `<done>` criteria were met without any Rule 1/2/3 auto-fixes or Rule 4 architectural escalations.

One environmental note (not a deviation from the plan's code scope): the local PostgreSQL 17 install's `bin/` directory (`C:\Program Files\PostgreSQL\17\bin`) had to be added to `PATH` for the session so `pytest-postgresql` could locate `pg_ctl`/`pg_config` to provision its ephemeral test cluster — this is a pre-existing environment requirement of the project's own test harness, not a code change.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. This is a pure code fix; no new environment variables, no schema migration.

## Next Phase Readiness

- HN, npm, PyPI, and changelog eligible items will now get a real `enrichments` row (summary + section) or an honest `fetch_failed` tombstone on the next scheduled Coolify run, instead of silently vanishing.
- Live confirmation against real Algolia/registry/RSS APIs is deferred to the deployed Coolify run (D4 above) — the local dev DB is GitHub-only per project memory, and this plan's test suite deliberately uses synthetic rows + fixtures with no live network call anywhere.
- The dashboard source-split/filter UI is explicitly out of scope here (per the plan's stated scope boundary) and remains a separate follow-up quick task if desired.

## Self-Check: PASSED

All created/modified files confirmed present on disk; all three task commit
hashes (`7f23d51`, `8cc1b9d`, `6cfbd05`) confirmed present in git log.

---
*Quick task: 260906-n5d*
*Completed: 2026-09-06*
