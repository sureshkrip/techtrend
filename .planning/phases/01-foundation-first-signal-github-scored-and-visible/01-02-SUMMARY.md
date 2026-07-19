---
phase: 01-foundation-first-signal-github-scored-and-visible
plan: 02
subsystem: dashboard
tags: [fastapi, jinja2, htmx, sqlite, ingest, wilson-score, walking-skeleton]

# Dependency graph
requires:
  - phase: 01-01
    provides: "techtrend.db.connection (connect/init_db), techtrend.config (load_config), techtrend.logging_setup (setup_logging), four-table SQLite schema, tests/conftest.py fixtures, tests/fixtures/github/repo_metadata.json"
provides:
  - "techtrend/ingest.py — python -m techtrend.ingest --fixture entry point, upserts entities+snapshots from the recorded GitHub fixture"
  - "techtrend/server/app.py + queries.py — read-only FastAPI dashboard (GET /), per-request DB connection, htmx HX-Request partial-vs-full-page branch, sqlite3.Error → DB-unreadable copy"
  - "techtrend/web/templates/{dashboard.html,partials/table.html} + static/{style.css,htmx.min.js} — UI-SPEC-compliant hand-authored templates and CSS custom properties, vendored htmx 2.0.4"
  - "tests/test_skeleton.py — five end-to-end assertions proving config→ingest→SQLite→FastAPI→Jinja2→browser"
affects: [github-collector, scoring-engine, health-strip]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sort-as-allow-dict: query_ranked never string-concatenates the sort query param into SQL; unrecognized values fall back to velocity (T-01-06 mitigation)"
    - "HX-Request header branch: same route returns partials/table.html to htmx and dashboard.html to a full page load, matching RESEARCH.md Pattern 5"
    - "Em-dash placeholder for not-yet-computed columns (velocity, stars gained) rather than a misleading zero — total stars is a real value pulled from the latest snapshot row via correlated subquery"
    - "sqlite3.Error caught in the route handler and rendered as the UI-SPEC DB-unreadable copy instead of a framework traceback (T-01-08 mitigation)"

key-files:
  created:
    - techtrend/ingest.py
    - techtrend/server/__init__.py
    - techtrend/server/app.py
    - techtrend/server/queries.py
    - techtrend/web/templates/dashboard.html
    - techtrend/web/templates/partials/table.html
    - techtrend/web/static/style.css
    - techtrend/web/static/htmx.min.js
    - tests/test_skeleton.py
  modified: []

key-decisions:
  - "Ran all commands through the project's own .venv (C:\\Users\\sures\\dev\\repos\\techtrend\\.venv) rather than the global Python interpreter — the global interpreter (used by an unrelated project on this machine) lacked jinja2/hishel and would have given false negatives"
  - "get_conn() calls connect() only, not init_db() — a missing/schema-less DB surfaces as the DB-unreadable error path (sqlite3.OperationalError is a sqlite3.Error subclass), not the empty-state path; the empty state is reserved for 'schema exists, zero rows,' matching the plan's explicit distinction between the two UI states"
  - "Docs-link fallback when docs_url is NULL (always true in this plan, since ingest.py doesn't populate it) uses the entity's own GitHub URL labeled 'Repo' — the honest D-15 fallback the ingest-side resolver will later populate directly via docs_url/docs_url_kind"

patterns-established:
  - "Pattern: FastAPI route handlers wrap the DB read in try/except sqlite3.Error and pass a db_error string into the template context rather than letting the exception propagate to a framework traceback"
  - "Pattern: query_ranked's ORDER BY is built from a fixed Python dict keyed by allowed sort values — the only string concatenation is of a dict VALUE the request can never influence, never of the request parameter itself"

requirements-completed: [DATA-01, DATA-02, DASH-01, DASH-04]

coverage:
  - id: D1
    description: "python -m techtrend.ingest --fixture writes a real, correctly-keyed entities row and snapshots row; re-running is idempotent"
    requirement: "DATA-01"
    verification:
      - kind: unit
        ref: "tests/test_skeleton.py#test_fixture_ingest_writes_entity_and_snapshot"
        status: pass
      - kind: manual_procedural
        ref: "python -m techtrend.ingest --fixture run twice; SELECT COUNT(*) unchanged between runs"
        status: pass
    human_judgment: false
  - id: D2
    description: "Snapshots append-only upsert keyed on (entity_id, collected_at, metric_name), stars metric written with source_kind='observed'"
    requirement: "DATA-02"
    verification:
      - kind: unit
        ref: "tests/test_skeleton.py#test_fixture_ingest_writes_entity_and_snapshot"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET / renders the seeded repo inside a <table>, 200 status, dashboard reads DB path from techtrend.config/connection module not a literal"
    requirement: "DASH-01"
    verification:
      - kind: unit
        ref: "tests/test_skeleton.py#test_dashboard_renders_seeded_repo"
        status: pass
      - kind: manual_procedural
        ref: "uvicorn techtrend.server.app:app + curl http://127.0.0.1:8123/ — verified real table row with 34521 stars rendered"
        status: pass
    human_judgment: false
  - id: D4
    description: "Each rendered row contains an anchor to the entity's GitHub URL (source link)"
    requirement: "DASH-04"
    verification:
      - kind: unit
        ref: "tests/test_skeleton.py#test_dashboard_row_links_to_source"
        status: pass
    human_judgment: false
  - id: D5
    description: "Zero-entity state renders the literal 'No data yet' empty state instead of a blank table, naming python -m techtrend.ingest"
    requirement: null
    verification:
      - kind: unit
        ref: "tests/test_skeleton.py#test_dashboard_empty_state"
        status: pass
    human_judgment: false
  - id: D6
    description: "GET / never writes — entities/snapshots/run_manifest row counts unchanged across a page render (D-17 read-only guarantee)"
    requirement: null
    verification:
      - kind: unit
        ref: "tests/test_skeleton.py#test_dashboard_never_writes"
        status: pass
    human_judgment: false
  - id: D7
    description: "UI-SPEC token compliance: CSS custom properties for spacing/typography/color, table-cell 8px/12px exception, no icon package, system font stack, no |safe filter on externally-sourced fields"
    requirement: null
    verification:
      - kind: unit
        ref: "acceptance-criteria greps (--space-md, --color-accent, #2563EB present; |safe absent) — run manually, all passed"
        status: pass
    human_judgment: true
    rationale: "Grep-verified literal token presence, but visual fidelity to the UI-SPEC (spacing rhythm, color application, typography hierarchy as actually rendered in a browser) was not screenshot-verified in this session — worth a human glance before treating the UI-SPEC as fully implemented, per the UI-SPEC's own 'not user-confirmed' footnote on colors/type/copy."

duration: 55min
completed: 2026-07-19
status: complete
---

# Phase 01 Plan 02: Walking Skeleton — Fixture Ingest to Rendered Dashboard Summary

**Closed the full config→ingest→SQLite→FastAPI→Jinja2→browser loop: `python -m techtrend.ingest --fixture` upserts a real GitHub entity/snapshot pair, and the FastAPI dashboard renders it as a table row with a working "View on GitHub" link, an honest em-dash for not-yet-scored columns, and a literal "No data yet" empty state.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-07-19T18:10:00Z (approx)
- **Completed:** 2026-07-19T19:17:38Z
- **Tasks:** 3 (TDD: RED, GREEN ingest, GREEN dashboard)
- **Files modified:** 9 (all new)

## Accomplishments
- Wrote `tests/test_skeleton.py`'s five end-to-end assertions first (RED), asserting on rendered HTTP/HTML content rather than internal function returns, so the tests break if any layer of the stack disconnects
- Built `techtrend/ingest.py`: `python -m techtrend.ingest --fixture` reads the recorded GitHub fixture, upserts one `entities` row (keyed `(source, source_native_id)`, `discovery_method='seed'`) and one `snapshots` row (`metric_name='stars'`, `source_kind='observed'`), logs one stage/count line, and is fully idempotent on re-run. Live collection is deliberately deferred to plan 01-03; the fixture branch remains as the permanent offline dev path
- Built `techtrend/server/queries.py`: `query_ranked` LEFT JOINs `entities` to `scores` with a fixed sort-allow-dict (never string-concatenating the request's `sort` param into SQL) and `query_latest_run` for the health strip's future data source — both pure SELECT, no write statements
- Built `techtrend/server/app.py`: single `GET /` route, per-request `connect()` dependency (never a shared cross-thread connection), `HX-Request` header branch between the full page and the table partial, and a `sqlite3.Error` handler rendering the UI-SPEC's DB-unreadable copy instead of a traceback
- Built `techtrend/web/templates/{dashboard.html,partials/table.html}` and `techtrend/web/static/style.css` implementing the UI-SPEC's spacing/typography/color token scale as CSS custom properties, the exact Copywriting Contract strings, and the D-15 docs-link honesty labeling (falls back to "Repo" when `docs_url_kind` is unresolved)
- Vendored `htmx.min.js` (2.0.4) as a local static file — no CDN dependency — proving the asset pipeline ahead of plan 01-06 wiring real sort interactivity
- Verified the true end-to-end path manually: ran `uvicorn techtrend.server.app:app` against a fixture-ingested DB and confirmed via `curl` a real 34,521-star `Aider-AI/aider` row, working source link, and 200 responses for both static assets

## Task Commits

1. **Task 1: Failing end-to-end skeleton test** - `354dd17` (test)
2. **Task 2: Fixture-backed ingest writes a real entity and snapshot** - `10d9b1c` (feat)
3. **Task 3: Read-only FastAPI dashboard renders the row in a browser** - `923308b` (feat)

_TDD gate compliance: RED (`test(01-02)`) precedes GREEN (`feat(01-02)` x2) in git log — verified._

## Files Created/Modified
- `techtrend/ingest.py` - `main(argv)` CLI entry point; `--fixture` flag; entity+snapshot upserts per RESEARCH.md Pattern 2
- `techtrend/server/__init__.py` - empty package marker
- `techtrend/server/app.py` - `app = FastAPI()`, `get_conn()` dependency, single `GET /` route, HX-Request branch, sqlite3.Error handling
- `techtrend/server/queries.py` - `query_ranked(conn, sort)`, `query_latest_run(conn)`, fixed sort-allow-dict
- `techtrend/web/templates/dashboard.html` - full page shell: title, placeholder health strip, table-or-empty-state
- `techtrend/web/templates/partials/table.html` - one `<tr>` per row, D-14 column set, em-dash placeholders, D-15 docs honesty label
- `techtrend/web/static/style.css` - UI-SPEC CSS custom properties (spacing/typography/color) and page/table/link rules
- `techtrend/web/static/htmx.min.js` - vendored htmx 2.0.4 (downloaded from unpkg, committed as a static asset)
- `tests/test_skeleton.py` - five end-to-end tests covering ingest write path, dashboard render, source link, empty state, and read-only guarantee

## Decisions Made
- Discovered and switched to the project's own `.venv` (`C:\Users\sures\dev\repos\techtrend\.venv`) for all test/ruff/ingest/uvicorn invocations — the machine's global `python` resolves to an interpreter shared with an unrelated project and is missing `jinja2`/`hishel`, which would have produced false import-error failures unrelated to this plan's code
- `get_conn()` intentionally calls `connect()` only, not `init_db()` — a missing/schema-less DB is treated as the DB-unreadable error state, not the empty-data state, keeping those two UI states honestly distinct as the UI-SPEC's error/empty state rows require
- Docs link falls back to the entity's own GitHub URL labeled "Repo" whenever `docs_url` is NULL (true for every row in this plan, since ingest.py doesn't populate `docs_url`/`docs_url_kind` — that's a later plan's concern) — implements D-15's honesty contract now so the template needs no rework when the resolver lands

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a false-positive grep match in test_skeleton.py's own docstring**
- **Found during:** Task 1 acceptance-criteria verification
- **Issue:** The module docstring's explanatory text literally contained the substrings `httpx.get`/`requests.get` (describing what the file does NOT do), which made the acceptance criterion's own `grep -c 'httpx.get\|requests.get'` return 1 instead of the required 0
- **Fix:** Reworded the docstring to describe the same guarantee without using those literal substrings
- **Files modified:** `tests/test_skeleton.py`
- **Verification:** `grep -c 'httpx\.get\|requests\.get' tests/test_skeleton.py` returns `0`
- **Committed in:** `354dd17` (Task 1 commit — fixed before commit)

**2. [Rule 1 - Bug] Fixed ruff B008 (Depends-in-default-argument) false positive**
- **Found during:** Task 3 `ruff check .` verification
- **Issue:** `techtrend/server/app.py`'s `dashboard()` route uses FastAPI's standard `conn: sqlite3.Connection = Depends(get_conn)` dependency-injection idiom, which ruff's `B008` rule flags as "don't call a function in an argument default" — a known false positive for FastAPI's own pattern
- **Fix:** Added a targeted `# noqa: B008` with an inline rationale comment rather than disabling B008 project-wide (which would also silence genuine mutable-default-argument bugs elsewhere)
- **Files modified:** `techtrend/server/app.py`
- **Verification:** `ruff check .` exits 0
- **Committed in:** `923308b` (Task 3 commit — fixed before commit)

**3. [Rule 1 - Bug] Reflowed two lines exceeding the 100-char ruff line-length limit**
- **Found during:** Task 2 `ruff check .` verification
- **Issue:** `FIXTURE_PATH` construction and a logger.info call in `techtrend/ingest.py` exceeded 100 characters (E501)
- **Fix:** Reflowed both across multiple lines
- **Files modified:** `techtrend/ingest.py`
- **Verification:** `ruff check .` exits 0
- **Committed in:** `10d9b1c` (Task 2 commit — fixed before commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1 — cosmetic/lint bugs required to satisfy the plan's own `verify` gate)
**Impact on plan:** No scope creep; all three were required to pass the plan's own stated acceptance criteria and `ruff check .` gate.

## Issues Encountered
None beyond the lint/grep fixes documented above.

## User Setup Required
None - no external service configuration required for this plan. The dashboard runs entirely against the local SQLite file; no GitHub token is needed since live collection is deferred to plan 01-03.

## Next Phase Readiness
- The Walking Skeleton is closed end-to-end: `python -m techtrend.ingest --fixture` followed by `uvicorn techtrend.server.app:app` yields a browser page showing a real repository row with a working source link, and an honest empty state with zero rows.
- Plan 01-03 (real GitHub collector) can replace `ingest.py`'s fixture branch with a live `httpx`+`hishel`+`tenacity` collector, writing into the same `entities`/`snapshots` upsert targets already proven here — no schema or query changes needed.
- Plan 01-04 (Wilson-bounded scoring) can start writing into `scores` immediately; `query_ranked`'s LEFT JOIN and em-dash placeholders were built specifically so populated `scores` rows appear with zero template changes.
- Plan 01-06 (health strip + real htmx sorting) has a placeholder `<div class="health-strip">` already reading `query_latest_run()`, and a vendored, working `htmx.min.js` asset ready to wire `hx-get`/`hx-target` onto the existing sort-header `<a>` tags.
- No blockers. `python -m pytest -q` is green (11 passed, 4 skipped — the remaining skips belong to plans 01-03/01-04/01-05/01-06) and `ruff check .` is clean.

---
*Phase: 01-foundation-first-signal-github-scored-and-visible*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 9 created files found on disk; all three task commits (`354dd17`, `10d9b1c`, `923308b`) found in git log.
