# Walking Skeleton — TechTrend

**Phase:** 1
**Generated:** 2026-07-19

## Capability Proven End-to-End

A user runs `python -m techtrend.ingest`, then opens `http://127.0.0.1:8000/` in a browser and sees a real GitHub repository rendered as a row in a ranked table, with a live "last successful run" freshness indicator above it.

This is the thinnest slice that exercises the entire stack: config file → HTTP collection → SQLite write → SQLite read → Jinja2 render → browser.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python 3.13 (floor 3.12) | Locked in `.claude/CLAUDE.md`. Local env verified at 3.13.5 with bundled SQLite 3.49.1 (well above the 3.24 floor `INSERT ... ON CONFLICT` needs). |
| Data layer | stdlib `sqlite3`, single file `techtrend.db`, `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000` | Zero-ops embedded DB. WAL lets the read-only dashboard render while the ingest process writes, with no lock contention and no second server process. No ORM. |
| Schema shape | Four tables: `entities`, `snapshots`, `scores`, `run_manifest` | Append-only snapshots separated from derived scores (DATA-02/DATA-03) so re-scoring never requires re-ingesting. `run_manifest` is the health substrate (HEALTH-01). |
| Identity key | `UNIQUE(source, source_native_id)` on `entities` | Deliberate v1 simplification — no cross-source entity resolution (deferred to v2). `source_native_id` is the GitHub numeric repo id, stable across renames. |
| Idempotency mechanism | `INSERT ... ON CONFLICT DO UPDATE` on both `entities` and `snapshots`, plus `PRIMARY KEY (run_date, stage)` on `run_manifest` | DATA-05 is a property of the schema, not of the caller. A partially-failed run is safe to re-run by construction. |
| Web layer | FastAPI + Jinja2 + htmx (vendored `htmx.min.js`, no CDN) | Locked in `.claude/CLAUDE.md`. No build step, no bundler, no client-side state. Sorting is a GET returning an HTML partial. |
| Styling | One hand-written `style.css` using CSS custom properties | Per `01-UI-SPEC.md` Design System — no CSS framework, no preprocessor, no npm icon package. Unicode glyphs only. |
| HTTP client | `httpx` + `hishel` (RFC 9111 cache → ETag/304 for free) + `tenacity` (retry/backoff) | COLL-07/COLL-08 are library concerns, not hand-rolled loops. `.claude/CLAUDE.md` explicitly forbids hand-rolled retry. |
| Config split | Secrets in `.env` (`python-dotenv`, gitignored); tunables/seed/allowlists in `config/tracked.toml` (stdlib `tomllib`, tracked in git) | Curation happens by hand-editing TOML, never through the UI (D-04, D-17). Read-only parsing is all that is needed, so `tomllib` adds no dependency. |
| Process model | Two independent processes: `python -m techtrend.ingest` (writer) and `uvicorn techtrend.server.app:app` (reader) | ARCHITECTURE.md's split-process variant. A crash in ingestion cannot take down the dashboard. The dashboard **never** triggers a pipeline run (D-17). |
| Directory layout | `techtrend/{collectors,pipeline,db,server,web}/` package with `tests/` alongside | Translates ARCHITECTURE.md's recommended structure into Python module shape. `collectors/registry.py` is the single file touched to add a source (COLL-06). |
| Deployment target | Local only — documented `uvicorn` run command, no hosting | Single-user local tool by design. Phase 4 adds a Windows Task Scheduler at-logon trigger; Phase 1 starts it by hand (D-17). |

## Stack Touched in Phase 1

- [ ] Project scaffold — `pyproject.toml` (deps + `[tool.ruff]` + `[tool.pytest.ini_options]`), package layout, `.env.example`, `config/tracked.toml`
- [ ] Routing — `GET /` (full page) and `GET /?sort=…` (htmx partial), served by FastAPI
- [ ] Database — real write (`entities` + `snapshots` upsert from live GitHub metadata) AND real read (dashboard join across `entities`/`scores`/`run_manifest`)
- [ ] UI — sortable column headers wired to htmx GET partial re-render; outbound source/docs anchors per row
- [ ] Deployment — documented local full-stack run: `python -m techtrend.ingest` then `uvicorn techtrend.server.app:app`

## Out of Scope (Deferred to Later Slices)

Explicitly NOT in the skeleton, so later phases do not re-litigate Phase 1's minimalism:

- Any LLM call, summary text, section taxonomy, or section filtering (Phase 2 — ENR-*, DASH-02)
- Hacker News, npm, PyPI, and RSS collectors (Phase 3 — COLL-03/04/05)
- Windows Task Scheduler registration, wake timers, run-if-missed (Phase 4 — SCHED-01/02)
- Cross-source entity resolution — a GitHub repo and its npm package stay two entities (v2)
- Sparklines in the table, a dedicated `/health` page, dual 7d/14d windows, EWMA smoothing or rank hysteresis (all deferred in `01-CONTEXT.md`)
- Pagination or virtualization of the ranked table (see planner assumption in `01-06-PLAN.md`)
- Authentication, multi-user, remote access, HTTPS — the server binds to `127.0.0.1` and has no login surface

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering the architectural decisions above:

- **Phase 2:** High-velocity items clearing the ranking gate get a grounded two-line summary and one of seven section labels, under a hard per-run LLM cost cap. Adds an `enrichments` table and a section filter to the existing table layout — no change to the collector interface or the scorer.
- **Phase 3:** Hacker News, npm/PyPI, and vendor changelogs appear alongside GitHub. Adds new modules under `collectors/` plus one line in `collectors/registry.py`, and implements the per-source normalization step already seamed in Phase 1 (D-13). No change to the scorer, gate, enricher, or dashboard.
- **Phase 4:** The full collect → score → enrich pipeline runs unattended daily via Windows Task Scheduler with wake/run-if-missed configured. Reuses the Phase 1 health strip as the missed-run indicator for free.
