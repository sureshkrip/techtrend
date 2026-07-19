# Phase 1: Foundation & First Signal — GitHub, Scored and Visible - Research

**Researched:** 2026-07-19
**Domain:** Greenfield Python data-pipeline + server-rendered dashboard (GitHub collector, SQLite time-series schema, Wilson-bounded velocity scoring, FastAPI/Jinja2/htmx dashboard)
**Confidence:** MEDIUM-HIGH overall — HIGH on GitHub API mechanics, SQLite patterns, and the Wilson-score math (verified/computed this session); MEDIUM on the FastAPI+htmx wiring and hishel's exact API surface (docs fetch was partially blocked, see Sources); **one CRITICAL finding requires a decision before planning proceeds** (see below).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Tracked Repo Universe**
- **D-01:** Repos enter the tracked set two ways: a hand-written **seed list** of repos the owner already cares about (Claude Code, GSD, Superpowers, Guardrails AI, Aider, etc.) **plus** a daily **GitHub search** over AI-coding topics/keywords that can promote newly-found repos into the set. Discovery is a first-class requirement, not just velocity tracking of a known list.
- **D-02:** Tracking is **sticky with quiet retirement**. Once a repo is admitted it is snapshotted every day thereafter regardless of whether it still appears in search results. A repo showing no meaningful star movement over a long window (suggest 90 days; make it config) is marked **dormant** and stops being polled, but its history is retained and it can wake back up.
- **D-03:** Relevance filtering for discovered repos is **fully deterministic** (Phase 1 has no LLM available). Admit a search hit if it carries any topic from a curated **topics allowlist** (`llm`, `ai-agents`, `mcp`, `rag`, `agentic`, `code-generation`, …) **OR** if its name/description matches a **keyword list**. Both lists live in config and are editable without a code change.
- **D-04:** Escape hatch is a **config force-include allowlist + force-exclude blocklist**. These live in the same config file as the seed list. The dashboard stays strictly read-only — curation happens in config, never the UI.

**Day-One Star History (Backfill)**
- **D-05:** Backfill uses **sampled stargazer pagination** against GitHub's own API — the `stargazers` endpoint with the `application/vnd.github.star+json` Accept header returns `starred_at` timestamps. Do **not** fetch every page; binary-search / sample pages to establish the recent slope. No third-party dependency (star-history.com, OSS Insight).
- **D-06:** Reconstruct **~90 days** of star accrual per repo, with a **hard per-repo request cap** (suggest ~20 stargazer page requests; make it config). If a repo is too large to resolve within the cap, accept a coarser curve rather than blowing the rate-limit budget.
- **D-07:** Backfilled points are written into the **same `snapshots` table** with the derived historical date as `collected_at`, plus a **`source_kind` provenance column** distinguishing `'backfill'` from `'observed'`. The existing `UNIQUE(entity_id, collected_at, metric_name)` constraint makes re-running the backfill idempotent for free (DATA-05).
- **D-08:** Backfill triggers **on first sight**. Per-repo completion is recorded (e.g. a `backfilled_at` column on the entity); a repo whose backfill failed or was truncated by the request cap is **retried on the next run** rather than being silently left with a stub history. Live daily snapshotting begins immediately regardless — **backfill failure must never block current data collection**.

**Ranking Formula**
- **D-09:** Velocity is computed over a **7-day trailing window**.
- **D-10:** The SCORE-03 absolute floor is on **stars gained within the window**, not on total star count (suggest N=25; make it config).
- **D-11:** Scoring uses a **Wilson-style lower confidence bound** (SCORE-02) so low-sample items are pulled toward zero.
- **D-12:** **No additional damping in Phase 1.** Ship window + Wilson bound, and **log a stability metric** each run (rank-overlap / Jaccard between consecutive runs' top-N).
- **D-13:** For SCORE-04 — **build the seam, calibrate later**. The source-specific step (raw metric → comparable momentum value) is distinct from the source-agnostic ranking step; GitHub implements it now, Phase 3 adds HN/npm/PyPI by implementing that step only.

**Dashboard & Health Display**
- **D-14:** The dashboard is a **dense sortable table** — rank, name, velocity score, stars gained in window, total stars, source link, docs link. Sorting via htmx GET returning an HTML partial.
- **D-15:** Docs-link resolution (DASH-05) is a **deterministic fallback chain**: GitHub `homepage` field → scan README for a link matching docs patterns → fall back to the repo URL itself, **labeled honestly as "repo" rather than "docs"**.
- **D-16:** Health/freshness is a **persistent header strip that escalates** (DASH-06, HEALTH-02). Always visible, showing "last successful run" as relative time. Escalates to a warning banner when stale (>36h), a collector failed, or GitHub returned zero items against a non-trivial trailing average.
- **D-17:** The dashboard is **started manually** (`uvicorn app:app`). With no data yet, render an **explicit empty state** ("No run has completed yet — run `python -m techtrend.ingest`"). The dashboard must **never** trigger a pipeline run on page load.

### Claude's Discretion
- Exact numeric values for config knobs (dormancy threshold, per-repo request cap, window-gain floor, staleness threshold) — shape decided, values are Claude's call, but every one must be **config, not a code constant**.
- The specific sampling algorithm for stargazer pagination (binary search vs. fixed stride vs. adaptive).
- Config file format and location (separate from `.env` secrets).
- Where `score_version` bookkeeping lives and how a formula change triggers a re-score.
- How release events (COLL-01) are represented alongside stars.
- Testing approach — two concrete assertions worth encoding: a synthetic 2→10-star item must not outrank a synthetic 4,000→4,300-star item; re-running a collection must not duplicate entities or snapshots.

### Deferred Ideas (OUT OF SCOPE)
- Sparklines in the dashboard table.
- Dedicated `/health` page over `run_manifest`.
- Dual 7d/14d window with spike detection.
- EWMA smoothing / rank hysteresis.
- No LLM calls, no summaries, no section taxonomy (Phase 2). No HN/npm/PyPI/RSS collectors (Phase 3). No Windows Task Scheduler wiring (Phase 4). No cross-source entity resolution (v2).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| DATA-01 | Canonical entity record, stable identity across runs | `entities` DDL below, keyed `UNIQUE(source, source_native_id)` |
| DATA-02 | Append-only timestamped snapshots for delta computation | `snapshots` DDL, `UNIQUE(entity_id, collected_at, metric_name)` |
| DATA-03 | Derived scores separate from snapshots, keyed to score_version | `scores` DDL + score_version bookkeeping section |
| DATA-05 | Partial-failure re-run is safe, no duplicate entities/snapshots | Upsert patterns + `run_manifest` idempotency section |
| COLL-01 | Collect GitHub star counts and release events | GitHub repo-metadata + Releases API section |
| COLL-02 | Backfill GitHub historical star data on first run | **Critical Finding** section — stargazer restriction + fallback design |
| COLL-06 | Adding a source = new collector module + registry entry | Collector Plugin Interface pattern (from ARCHITECTURE.md, restated in Python) |
| COLL-07 | Authenticate, respect rate limits, back off | GitHub rate-limit table + tenacity retry pattern |
| COLL-08 | Conditional requests (ETag/If-None-Match) | hishel caching pattern + verified 304 behavior |
| COLL-09 | Resolve to existing entity or create new one | Entity upsert SQL |
| SCORE-01 | Rank by velocity over multi-day window, not absolute counts | 7-day window gain computation |
| SCORE-02 | Confidence-bounded score (Wilson lower bound) | Wilson formula + worked validation |
| SCORE-03 | Absolute minimum threshold before ranking | Floor+Wilson combination — validated against pitfall test case |
| SCORE-04 | Cross-source score normalization seam | Normalization seam design (D-13) |
| SCORE-05 | Day-to-day rank stability | Stability metric (Jaccard) design |
| DASH-01 | View ranked items in local dashboard | FastAPI+Jinja2+htmx minimal layout |
| DASH-03 | Sort by velocity score | htmx GET partial re-render pattern |
| DASH-04 | Click through to original source | `entities.url` column |
| DASH-05 | Reach docs/getting-started page | Docs-link resolution chain (D-15) code |
| DASH-06 | Show last successful refresh | `run_manifest` query + header strip pattern |
| HEALTH-01 | Record per-source success/failure/item counts | `run_manifest` DDL |
| HEALTH-02 | Surface a dead/stale source visibly | Escalating health banner logic |
</phase_requirements>

## Summary

Phase 1 is a from-scratch build: SQLite schema, one GitHub collector, a confidence-bounded velocity scorer, and a read-only FastAPI/Jinja2/htmx dashboard. The approved stack (Python 3.12/3.13, stdlib `sqlite3` + WAL, FastAPI/Jinja2/htmx, httpx+hishel+tenacity, pydantic v2) is current and verified against PyPI as of this session — no changes recommended there.

**One finding is critical and must be resolved before planning locks in D-05/D-06/D-07/D-08 as written:** GitHub restricted the `stargazers`-with-timestamp endpoint (the exact mechanism D-05 specifies) to a repo's own admins/collaborators as of late June/July 2026 — see **Critical Finding** below. For the vast majority of repos this dashboard will track (Claude Code, Aider, LangGraph, etc. — none owned by the dashboard's operator), the sampled-stargazer-pagination approach as literally specified will return `403`/`404` on every call. This does **not** affect live daily star-count polling (COLL-01/D-02), only the day-one historical backfill (COLL-02/D-05–D-08). A concrete fallback is proposed below; this needs explicit confirmation before or during planning, not silent workaround.

Everything else validates cleanly: the Wilson-lower-bound + absolute-floor combination (D-10/D-11) was hand-computed against the exact pitfall test case ("a synthetic 2→10-star item must not outrank a synthetic 4,000→4,300-star item") and passes **only when both mechanisms are applied together** — Wilson bound alone does not save it. SQLite's `INSERT...ON CONFLICT` upsert pattern gives idempotency for free on both `entities` and `snapshots`. FastAPI+Jinja2+htmx sort-as-GET-partial is a well-trodden, simple pattern with no build step.

**Primary recommendation:** Build the schema and collector exactly as specified in ARCHITECTURE.md/CONTEXT.md, but implement GitHub backfill (D-05) as "attempt real stargazer sampling; on `403 Forbidden` fall back to a documented degraded state" rather than assuming it always succeeds — and get explicit sign-off on that fallback's shape (see Critical Finding → Recommended Path) before treating COLL-02 as fully specified.

## Critical Finding: GitHub Restricted the Stargazers-Timestamp Endpoint (June/July 2026)

**What changed:** GitHub's official changelog (published 2026-06-30, "Upcoming access restrictions to public API endpoints and UI views") announced that the `GET /repos/{owner}/{repo}/stargazers` endpoint (the one D-05 specifies, with the `application/vnd.github.star+json` Accept header for `starred_at`) and the `GET /repos/{owner}/{repo}/subscribers` (watchers) endpoint are now **limited to a repository's own admins and collaborators**. `[CITED: github.blog/changelog/2026-06-30-upcoming-access-restrictions-to-public-api-endpoints-and-ui-views]`

Independent confirmation from a tool that broke because of this change: star-history.com's own incident post states plainly, *"GitHub no longer exposes this star data to anyone but the repo's admins and collaborators, so these charts are broken for now,"* and that for any repo you don't own/collaborate on, an authenticated request now returns "Not Found." `[CITED: star-history.com/blog/github-stargazer-api-restriction]` The same restriction applies to the GraphQL equivalent (`stargazers(orderBy: {field: STARRED_AT})`) — it is not a REST-only quirk. `[CITED: github.com/orgs/community discussions on the same changelog]`

**What is NOT affected:** the repo-metadata endpoint (`GET /repos/{owner}/{repo}`, returning `stargazers_count`, `topics`, `homepage`, etc.) and the Search API (`GET /search/repositories`) are untouched — these are what COLL-01's daily live collection and D-01/D-03's discovery search actually use. **Only the historical-backfill mechanism (COLL-02, D-05–D-08) is blocked**, and only for repos the tool's operator doesn't own/collaborate on — i.e., nearly the entire tracked set outside possibly the owner's own GSD/Superpowers repos.

**Why this matters for this phase specifically:** D-06's stated rationale for 90 days of backfill was explicitly "enough baseline to judge whether current growth is unusual for that repo... Roadmap Success Criterion #1 depends on this working on day one ("Opening the dashboard shows a ranked list... ordered by velocity, where a small repo gaining stars quickly outranks a large repo gone flat" — reachable *before any LLM cost*, i.e., on first open). Without backfill, every tracked entity starts with zero history and no 7-day window exists until a week of live daily runs accrues.

### Options

| Option | Description | Tradeoff |
|--------|-------------|----------|
| **A. Graceful per-repo fallback (recommended default)** | Attempt D-05 as specified; catch `403`/`404` explicitly (not a transient error — do **not** retry per D-08's retry logic, which is meant for transient/rate-limit failures); record `backfill_status='blocked'` on the entity. Entities with no real history are either (a) excluded from ranking until they accrue enough live snapshots for a partial window, shown in the table with an honest "building history" marker instead of a rank, or (b) ranked on whatever partial window is available (1-6 days) with `window_days` recorded in `scores` for transparency. | Keeps the approved stack unchanged, zero new infrastructure. Roadmap Success Criterion #1 is met only partially on day one (repos the owner does own/collaborate on, if any, get real backfill; everything else needs ~1 week to build a meaningful window). Consistent with the project's own "honest labeling over silent wrongness" pattern already established for docs-links and empty states (Specific Ideas in CONTEXT.md). |
| **B. GH Archive (BigQuery public dataset)** | GH Archive (`gharchive.org`) is a long-running (since 2011), independently-hosted archive of GitHub's own public Events API, including `WatchEvent` (fires on every star). Query the BigQuery public dataset filtering `type='WatchEvent'` and `repo.name` for the tracked repos, scoped to a date range — well within BigQuery's free 1TB-scanned/month tier for a few dozen repos over 90 days. `[CITED: gharchive.org, github.com/igrigorik/gharchive.org]` | Recovers real backfill for **any** public repo regardless of ownership — the only option that does. But requires a new external dependency not in the approved stack: a Google Cloud project + `google-cloud-bigquery` client + credentials, which is materially more setup than "a local Python + SQLite tool." This is the kind of infrastructure addition CONTEXT.md's D-05 explicitly reasoned against when it rejected third-party star-history services (though GH Archive's risk profile is different — it mirrors GitHub's own public event stream rather than a derived/computed metric, and is widely used in the peer-reviewed fake-star research already cited in PITFALLS.md). **Recommend surfacing this as an explicit, separate decision to the user rather than silently adopting it** — it changes the phase's dependency footprint. |
| **C. Accept no real backfill; naive day-1 fallback** | Per ARCHITECTURE.md's own Build Order caveat (step 3), use a naive day-1 score (rank by absolute current value) until real snapshot history accrues, with no backfill component at all. | Simplest, but throws away D-06's explicit design intent and the "reachable before any LLM cost" success criterion loses its "genuine velocity, not raw count" property on day one — the exact thing Phase 1 exists to prove. |

**Recommendation for planning:** Implement Option A as the Phase 1 default (no new infrastructure, degrades honestly, ships this week), and raise Option B explicitly as a discussion item — either in a follow-up `/gsd-discuss-phase` pass on this phase or as a fast-follow decision — since it is the only option that fully satisfies D-06's original intent. **Do not silently implement Option A and claim COLL-02/D-05 are satisfied as originally written** — they are satisfied in degraded form only.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| GitHub data collection (stars, releases, search discovery) | Backend / Ingestion script | — | Runs as a standalone process (`python -m techtrend.ingest`), no web request involved; owns all GitHub auth/rate-limit/pagination logic |
| Entity identity resolution | Backend / Ingestion (pipeline stage) | Database | Pure function over `(entities, incoming record)`; writes via upsert |
| Snapshot storage | Database (SQLite) | — | Append-only; the ingestion script is the only writer |
| Velocity scoring (Wilson + floor) | Backend / Pipeline (standalone, no I/O) | Database | Pure function of `(entities, snapshots)`; independently re-runnable |
| Health/run bookkeeping | Backend / Pipeline (orchestrator) | Database | Written by the orchestrator at each stage boundary |
| Dashboard rendering | Backend Server (FastAPI, SSR) | Browser (htmx interactivity only) | FastAPI reads DB and renders Jinja2 templates; htmx only triggers new GET requests, no client-side state |
| Sort/filter interactivity | Browser (htmx triggers) | Backend Server (re-renders partial) | Sorting is a GET request re-render, not client-side JS logic — no state lives in the browser |
| Docs-link resolution | Backend / Ingestion (pipeline stage) | — | Computed once at collection time from GitHub metadata + README text, stored on `entities`, not resolved at render time |

## Project Constraints (from CLAUDE.md)

- **Locked stack:** Python 3.12/3.13; stdlib `sqlite3` (WAL mode); FastAPI + Jinja2 + htmx (CDN or vendored); `httpx` + `hishel` + `tenacity`; `pydantic` v2; `uvicorn`; `ruff`; `pytest`; `uv` or `pip`+`venv`. Do not introduce a different web framework, ORM, or SPA toolchain.
- **Forbidden:** `cron` (doesn't exist natively on Windows), Celery/Redis/RabbitMQ, PostgreSQL, any SPA framework, `scrapy`, hand-rolled retry loops, a hand-written sleep-loop "scheduler."
- **GSD workflow enforcement:** File-changing work must go through a GSD command (`/gsd-execute-phase`, `/gsd-quick`, `/gsd-debug`) — not a constraint on *what* to build, but on *how* work in this repo proceeds; the planner should structure tasks assuming this gate exists.
- **No LLM calls in Phase 1** — `anthropic` SDK, if installed at all, is unused until Phase 2.
- Project skills directory is empty; no additional project-specific conventions beyond CLAUDE.md exist yet.

## Standard Stack

### Core

| Library | Version (verified 2026-07-19) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 or 3.13 | Runtime | Locked in CLAUDE.md. Local environment already has 3.13.5 with stdlib SQLite 3.49.1 (well above the 3.24 minimum for `INSERT...ON CONFLICT`). `[VERIFIED: local `python --version`/`sqlite3.sqlite_version`]` |
| `fastapi` | 0.139.2 | Dashboard web framework | `[VERIFIED: PyPI registry — pip index versions]`. Package identity/choice inherited from locked CLAUDE.md stack, not re-litigated here. |
| `uvicorn` | 0.51.0 | ASGI server | `[VERIFIED: PyPI registry]` |
| `jinja2` | 3.1.6 | Templating | `[VERIFIED: PyPI registry]` |
| `httpx` | 0.28.1 | HTTP client (sync, used for GitHub collector) | `[VERIFIED: PyPI registry]` |
| `hishel` | 1.3.0 (1.2.1 was current per STACK.md; 1.3.0 has since shipped) | RFC 9111 HTTP caching layer for `httpx` — gives ETag/If-None-Match handling for free (COLL-08) | `[VERIFIED: PyPI registry]` |
| `tenacity` | 9.1.4 | Retry/backoff decorator (COLL-07) | `[VERIFIED: PyPI registry]` |
| `pydantic` | 2.13.4 | Validate ingested GitHub records | `[VERIFIED: PyPI registry]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | 1.2.2 | Load `GITHUB_TOKEN` from `.env` | Always — secrets never in the tracked config file |
| stdlib `tomllib` | bundled (3.11+) | Read-only parser for the non-secret tunables/seed/allowlist config file | Recommended for the "config file format" discretion item — no new dependency, read-only is exactly what's needed since curation happens by hand-editing the file, never via the app |
| stdlib `logging` | bundled | Structured log-to-file for the ingestion script | Always — Task Scheduler (Phase 4) runs this headless; a log file is the only way to debug it later |
| `feedparser`, `APScheduler` | (see STACK.md) | Not needed in Phase 1 | Phase 3 (RSS) / Phase 4 (in-process scheduler, if ever used) respectively |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `tomllib` for config | `pyyaml` (YAML config) | YAML is marginally more readable for nested allowlists, but adds a dependency for a read-only file the owner hand-edits rarely; TOML's flat table syntax is a fine fit for seed lists/allowlists/tunables. Use YAML only if the config nesting grows complex enough that TOML becomes awkward. |
| stdlib `sqlite3` (per-request connection) | `aiosqlite` | Only needed if the dashboard becomes async-heavy; for a single local user reading a small SQLite file, sync stdlib `sqlite3` with WAL + a busy-timeout PRAGMA is simpler and sufficient. `[CITED: general FastAPI/SQLite concurrency guidance, cross-corroborated]` |
| Native GitHub stargazers backfill (D-05) | GH Archive / BigQuery | See Critical Finding above — this is a live open decision, not a settled alternative. |

**Installation:**
```bash
pip install fastapi uvicorn jinja2 httpx hishel tenacity pydantic python-dotenv
pip install ruff pytest
# tomllib and sqlite3 are stdlib — no install needed (Python 3.11+)
```

**Version verification performed this session:** all core packages confirmed present and current via `pip index versions <pkg>` against the live PyPI index (see table above); no package name substitutions or hallucination risk detected — all resolve to their expected, long-established GitHub org repos (`fastapi/fastapi`, `Kludex/uvicorn`, `pallets/jinja`, `encode/httpx`, `karpetrosyan/hishel`, `jd/tenacity`, `pydantic/pydantic`, `theskumar/python-dotenv`).

## Package Legitimacy Audit

| Package | Registry | Age (release history) | Downloads | Source Repo | Verdict (automated) | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| fastapi | pypi | 260+ releases back to 0.1.0 | unknown-downloads (sandbox has no telemetry access) | github.com/fastapi/fastapi | SUS | **Approved** — already locked in CLAUDE.md; SUS driven entirely by "unknown-downloads"/"too-new" signals the check tool cannot resolve in this sandbox, not by any real risk indicator |
| uvicorn | pypi | 190+ releases back to 0.0.1 | unknown-downloads | github.com/Kludex/uvicorn | SUS | **Approved** — same reasoning |
| jinja2 | pypi | 40+ releases back to 2.0 | unknown-downloads | github.com/pallets/jinja | SUS | **Approved** — same reasoning; Pallets project, multi-year history |
| httpx | pypi | 60+ releases back to 0.6.7 | unknown-downloads | github.com/encode/httpx | SUS | **Approved** — same reasoning; Encode org, well-established |
| hishel | pypi | 40+ releases back to 0.0.1 | unknown-downloads | github.com/karpetrosyan/hishel | SUS | **Approved** — same reasoning; smaller project but active, matches CLAUDE.md's already-researched pick |
| tenacity | pypi | 30+ releases back to 2.0.0 | unknown-downloads | github.com/jd/tenacity | SUS | **Approved** — same reasoning |
| pydantic | pypi | 150+ releases back to 0.1 | unknown-downloads | github.com/pydantic/pydantic | SUS | **Approved** — same reasoning |
| python-dotenv | pypi | 50+ releases back to 0.1.0 | unknown-downloads | github.com/theskumar/python-dotenv | SUS | **Approved** — same reasoning |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all 8 core packages flagged, but every flag traces to the legitimacy-check tool's inability to fetch PyPI download counts in this sandboxed session ("unknown-downloads") rather than to any genuine slopsquat/hallucination signal — every package resolves to its long-established, multi-year, correctly-named official GitHub org repo, confirmed via a direct `pip index versions` registry lookup. **Per protocol, the planner should still insert a lightweight `checkpoint:human-verify` before the dependency-install task** given the mechanical SUS verdict, but this should be a fast rubber-stamp, not a deep investigation — these are the same packages already named and researched in the project's own locked `CLAUDE.md`/`STACK.md`.

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────┐
                         │   config/tracked.toml        │
                         │  (seed list, topics/keyword   │
                         │   allowlist, force-in/out,    │
                         │   window/floor/cap tunables)  │
                         └──────────────┬───────────────┘
                                        │ read at ingest start
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  INGEST (python -m techtrend.ingest — run manually in Phase 1)      │
 │                                                                       │
 │  1. Discovery: GitHub Search API (topics/keyword query)  ──┐         │
 │     + seed list + force-include/force-exclude              │         │
 │                                                              ▼         │
 │  2. GitHubCollector.fetch(repo) ──► repo metadata (stars, homepage,  │
 │     topics, releases) via httpx+hishel (ETag-cached) + tenacity retry│
 │                                                              │         │
 │  3. Identity resolve: match (source, source_native_id)      │         │
 │     or INSERT new entity row  ───────────────────────────────┤         │
 │                                                              ▼         │
 │  4. Backfill (first-sight only): stargazer sampling attempt;         │
 │     on 403/404 → mark backfill_status='blocked', continue           │
 │                                                              │         │
 │  5. Snapshot write: UPSERT into snapshots                    │         │
 │     (entity_id, collected_at=today, metric_name='stars', …) │         │
 │                                                              ▼         │
 │  6. run_manifest: record per-stage success/failure/item_count        │
 └──────────────────────────────┬────────────────────────────────────────┘
                                 │ writes to SQLite (WAL mode)
                                 ▼
                    ┌───────────────────────────┐
                    │  entities / snapshots /    │
                    │  scores / run_manifest     │
                    │  (SQLite file, single DB)  │
                    └─────────────┬─────────────┘
                                  │ read-only
                                  ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  SCORE (python -m techtrend.score — standalone, no network I/O)     │
 │  For each entity: compute 7-day window gain from snapshots,          │
 │  apply SCORE-03 floor, apply Wilson lower bound (SCORE-02),          │
 │  write/replace rows in `scores` keyed by score_version               │
 └──────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  SERVE (uvicorn app:app — started manually, read-only)               │
 │  GET /             → full page: table + health header strip         │
 │  GET /?sort=…      → htmx partial re-render of table body only       │
 │  Reads: entities ⋈ scores ⋈ latest run_manifest row                  │
 │  Never triggers ingest/score — pure downstream reader                │
 └─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
techtrend/
├── techtrend/
│   ├── __init__.py
│   ├── config.py              # tomllib load of config/tracked.toml + pydantic validation
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── base.py            # Collector protocol/ABC (COLL-06 plugin seam)
│   │   ├── github.py          # GitHub collector: search, repo metadata, releases, backfill
│   │   └── registry.py        # the one file touched to add a source
│   ├── pipeline/
│   │   ├── identity.py        # match-or-create entity
│   │   ├── snapshot.py        # upsert into snapshots
│   │   ├── score.py           # pure function of (entities, snapshots) → scores
│   │   ├── stability.py       # Jaccard rank-overlap metric (D-12)
│   │   └── orchestrator.py    # drives ingest run, writes run_manifest
│   ├── db/
│   │   ├── schema.sql
│   │   └── connection.py      # WAL pragma, busy_timeout, per-call connection helper
│   ├── server/
│   │   ├── app.py             # FastAPI app, routes
│   │   └── queries.py         # read-only SQL for dashboard
│   ├── web/
│   │   ├── templates/
│   │   │   ├── dashboard.html
│   │   │   └── partials/table.html
│   │   └── static/htmx.min.js
│   └── ingest.py              # entry point: python -m techtrend.ingest
├── config/
│   └── tracked.toml           # seed list, topics/keywords, force-in/out, tunables (not secret)
├── .env                        # GITHUB_TOKEN (gitignored)
├── tests/
│   ├── test_score.py           # Wilson+floor pitfall assertions
│   ├── test_idempotency.py     # duplicate entity/snapshot assertions
│   └── fixtures/
├── pyproject.toml
└── techtrend.db                 # SQLite file (gitignored)
```

### Pattern 1: Collector Plugin Interface (Python translation of ARCHITECTURE.md)

**What:** A `Collector` protocol every source implements; `registry.py` is the only file the orchestrator iterates.
**When to use:** From the first collector — Phase 3's success criterion depends on this boundary being correct now.
```python
# collectors/base.py
from typing import Protocol
from datetime import date

class Collector(Protocol):
    source_id: str  # "github"
    def fetch(self, since: date) -> list[dict]: ...
    def normalize(self, raw: dict) -> "CollectedItem": ...

# collectors/registry.py — the ONLY file touched to add a source
from .github import GitHubCollector
COLLECTORS: list[Collector] = [GitHubCollector()]

# pipeline/orchestrator.py — never branches on source
for collector in COLLECTORS:
    try:
        raw_items = collector.fetch(run_date)
        for raw in raw_items:
            item = collector.normalize(raw)
            identity_resolve_and_snapshot(item, run_date)
        record_run_manifest(run_date, f"collect:{collector.source_id}", "success", len(raw_items))
    except Exception as exc:
        record_run_manifest(run_date, f"collect:{collector.source_id}", "failed", error=str(exc))
```

### Pattern 2: Append-Only Snapshot + Derived Score (SQLite DDL)

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE entities (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,                    -- 'github'
    source_native_id TEXT NOT NULL,          -- GitHub repo numeric id (stable across renames)
    full_name TEXT NOT NULL,                 -- 'owner/repo'
    url TEXT NOT NULL,
    homepage TEXT,
    docs_url TEXT,
    docs_url_kind TEXT,                      -- 'homepage' | 'readme' | 'repo'  (D-15)
    discovery_method TEXT NOT NULL,          -- 'seed' | 'search' | 'force-include'
    admitted_at TEXT NOT NULL,               -- ISO8601
    last_seen_at TEXT NOT NULL,
    dormant_at TEXT,                         -- D-02
    backfilled_at TEXT,                      -- D-08
    backfill_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'complete'|'blocked'|'failed'
    force_excluded INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source, source_native_id)
);

CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    collected_at TEXT NOT NULL,              -- ISO8601 date, day granularity
    metric_name TEXT NOT NULL,               -- 'stars' | 'releases'
    metric_value INTEGER NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'observed',  -- 'observed' | 'backfill'  (D-07)
    UNIQUE(entity_id, collected_at, metric_name)
);
CREATE INDEX idx_snapshots_entity_date ON snapshots(entity_id, collected_at);

CREATE TABLE scores (
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    run_date TEXT NOT NULL,
    score_version INTEGER NOT NULL,
    stars_gained INTEGER NOT NULL,
    window_days INTEGER NOT NULL,            -- may be <7 for a fresh entity
    wilson_lower_bound REAL NOT NULL,
    eligible INTEGER NOT NULL,               -- 0/1 — cleared SCORE-03 floor
    PRIMARY KEY (entity_id, run_date, score_version)
);

CREATE TABLE run_manifest (
    run_date TEXT NOT NULL,
    stage TEXT NOT NULL,                     -- 'collect:github' | 'backfill:github' | 'score'
    status TEXT NOT NULL,                    -- 'success' | 'failed' | 'zero_items'
    item_count INTEGER,
    error_detail TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    PRIMARY KEY (run_date, stage)
);
```

**Upsert (idempotent re-run, DATA-05):**
```sql
-- entities: match-or-create (COLL-09)
INSERT INTO entities (source, source_native_id, full_name, url, homepage, discovery_method, admitted_at, last_seen_at)
VALUES (:source, :native_id, :full_name, :url, :homepage, :method, :now, :now)
ON CONFLICT(source, source_native_id) DO UPDATE SET
    full_name = excluded.full_name,
    url = excluded.url,
    homepage = excluded.homepage,
    last_seen_at = excluded.last_seen_at;

-- snapshots: append-only, safe to re-run same-day collection
INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value, source_kind)
VALUES (:entity_id, :today, 'stars', :count, 'observed')
ON CONFLICT(entity_id, collected_at, metric_name) DO UPDATE SET
    metric_value = excluded.metric_value;
```
`[CITED: sqlite.org/lang_conflict.html — ON CONFLICT clause, available since SQLite 3.24.0 (2018); local environment has 3.49.1]`

### Pattern 3: Velocity Scoring — Floor + Wilson Bound, Validated Against the Pitfall Test

**Formula.** For each entity: `p̂ = stars_gained_in_window / stars_total_now`, `n = stars_total_now`. Compute the Wilson lower bound of `p̂` at 95% confidence (z=1.96):

```python
import math

def wilson_lower_bound(successes: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    phat = successes / n
    denom = 1 + z**2 / n
    center = phat + z**2 / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n)
    return max(0.0, (center - margin) / denom)

def score_entity(stars_gained: int, stars_total: int, floor: int) -> tuple[bool, float]:
    """Returns (eligible, wilson_lower_bound). eligible=False → excluded from ranking (SCORE-03)."""
    if stars_gained < floor or stars_total <= 0:
        return False, 0.0
    n = stars_total
    successes = min(stars_gained, n)
    return True, wilson_lower_bound(successes, n)
```
`[CITED: Wilson score interval — well-established statistical method, cross-referenced in PITFALLS.md and multiple independent explainer sources]`

**Worked validation (computed this session, z=1.96) — this is the exact assertion named in CONTEXT.md's testing discretion item:**

| Case | stars_gained | stars_total | Passes SCORE-03 floor (N=25)? | Wilson lower bound |
|------|------|------|------|------|
| 2→10 stars | 8 | 10 | **No** (8 < 25) → excluded entirely | 0.490 if computed anyway (would rank *above* the big repo on Wilson alone!) |
| 50→75 stars | 25 | 75 | Yes (25 ≥ 25) | 0.237 |
| 4,000→4,300 stars | 300 | 4,300 | Yes | 0.0625 |

**This is the load-bearing finding for SCORE-02/SCORE-03:** the Wilson bound alone does **not** solve Pitfall #2 — a 2→10 item's Wilson lower bound (0.490) is *higher* than the 4,000→4,300 item's (0.0625), because a small repo where "most of its stars are recent" has a legitimately high `p̂`. **The absolute floor (D-10, SCORE-03) is what excludes the 2→10 item from ranking at all; Wilson bound only differentiates among items that already cleared the floor.** Both mechanisms are required together — this must be encoded as a test (`stars_gained < floor` excludes regardless of `p̂`), not just documented. The 50→75 case shows the intended behavior once both apply: a small repo that tripled its stars in a week (0.237) correctly outranks a large repo growing only 7% (0.0625) — satisfying Roadmap Success Criterion #1's "a small repo gaining stars quickly outranks a large repo that has gone flat."

**Day-1 / partial-window handling:** an entity with fewer than 7 days of snapshots computes `stars_gained` over whatever range exists (`MAX(metric_value) - MIN(metric_value)` across all available `snapshots` rows for that entity, whether `source_kind='backfill'` or `'observed'`), and records the actual `window_days` used in `scores` for transparency. This is what makes the Critical Finding's Option A (graceful degradation) mechanically work: an entity with zero backfill and one day of live data has `window_days=1` and (almost always) `stars_gained` below the floor, so it is honestly excluded rather than falsely ranked.

**This framing (`p̂ = gain/total`, `n = total`) is itself a design choice, not a single canonical published formula** — Wilson score intervals are classically defined over binary success/failure trials (e.g., upvote/downvote), and there is no universally standard way to map "stars gained in a window" onto that shape. `[ASSUMED — see Assumptions Log A1]` The planner should encode the two worked test cases above as literal `pytest` assertions before trusting this formula in production.

### Pattern 4: GitHub Collector — HTTP, Auth, Conditional Requests

**Rate limits (verified against official GitHub docs this session):**

| Endpoint class | Authenticated limit | Unauthenticated limit | Notes |
|---|---|---|---|
| Core REST API (repo metadata, releases) | 5,000 req/hour | 60 req/hour | `[VERIFIED: docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api]` |
| Search API (`/search/repositories`) | 30 req/minute | 10 req/minute | Separate, much stricter budget from core `[VERIFIED: docs.github.com/en/rest/search/search]`. Max 1,000 results per query, 100/page. |
| Conditional requests (ETag/If-None-Match) | 304 responses **do not count** against the primary rate limit, provided the request is authenticated | — | `[VERIFIED: docs.github.com/rest/guides/best-practices-for-using-the-rest-api]` |
| Stargazers-with-timestamp (`/repos/{o}/{r}/stargazers` + star+json Accept) | **Admins/collaborators only, as of June/July 2026** | blocked | See Critical Finding |

```python
import httpx, hishel, tenacity

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]  # from .env via python-dotenv, never committed

storage = hishel.SQLiteStorage()  # confirm exact constructor kwargs against hishel's docs at
                                   # install time — this session's docs fetch was partially
                                   # blocked (see Sources); the sqlite/file/redis storage
                                   # backends and CacheClient/CacheTransport wrapper pattern
                                   # are confirmed to exist, exact kwargs are [CITED] not [VERIFIED]
client = hishel.CacheClient(
    storage=storage,
    headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "techtrend/0.1 (contact: sureshkrip@gmail.com)",
    },
)

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        # 403 with rate-limit headers or 5xx are retryable; 403 permission-denied (backfill
        # restriction) and 404 are NOT — those are permanent, handled by the caller instead.
        resp = exc.response
        if resp.status_code >= 500:
            return True
        if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
            return True
    return False

@tenacity.retry(
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_exponential(multiplier=2, min=2, max=60),
    retry=tenacity.retry_if_exception(_is_retryable),
)
def fetch_repo_metadata(full_name: str) -> dict:
    resp = client.get(f"https://api.github.com/repos/{full_name}")
    resp.raise_for_status()
    return resp.json()
```
`[CITED: docs.github.com rate-limit/best-practices pages (rate limits, ETag behavior); hishel.com + github.com/karpetrosyan/hishel (storage backends, CacheClient/CacheTransport existence, exact kwargs not independently confirmed this session); tenacity.readthedocs.io (retry/backoff decorator shape)]`

**Discovery search query shape (D-01/D-03):**
```
GET https://api.github.com/search/repositories?q=topic:llm+topic:ai-agents+topic:mcp&sort=stars&order=desc&per_page=100
```
Combine with a second pass using `in:name,description,readme` for the keyword-fallback list, since brand-new repos often carry no topics yet (D-03's stated rationale).

### Pattern 5: FastAPI + Jinja2 + htmx — Sort as GET Partial Re-render

```python
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="techtrend/web/templates")

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, sort: str = "velocity"):
    rows = query_ranked(sort)  # read-only SQL against entities ⋈ scores
    health = query_latest_run_manifest()
    template = "partials/table.html" if request.headers.get("HX-Request") else "dashboard.html"
    return templates.TemplateResponse(
        template, {"request": request, "rows": rows, "sort": sort, "health": health}
    )
```
```html
<!-- dashboard.html header -->
<th><a hx-get="/?sort=velocity" hx-target="#table-body" hx-push-url="true">Velocity</a></th>
<tbody id="table-body">{% include "partials/table.html" %}</tbody>
```
`[CITED: blakecrosley.com/guides/fastapi-htmx; testdriven.io/blog/fastapi-htmx — HX-Request header check + partial-vs-full-page pattern, cross-corroborated across multiple independent write-ups]`

**Concurrency note:** the dashboard only ever reads; the ingest/score scripts only ever write, and run as a separate process, not started by the dashboard (D-17). With `PRAGMA journal_mode=WAL` and a `busy_timeout`, this read-while-write pattern needs no additional locking — WAL allows concurrent readers during a writer's transaction. Use one `sqlite3.connect(...)` per FastAPI request (via `Depends`), never a single connection shared across threads (`check_same_thread=True`, the default, enforces this). `[CITED: general FastAPI+SQLite concurrency guidance, cross-corroborated across multiple sources this session]`

### Pattern 6: Docs-Link Resolution Chain (D-15)

```python
DOCS_PATTERNS = ("docs.", "/docs", "documentation", "getting-started", "getting_started", "quickstart")

def resolve_docs_url(repo_meta: dict, readme_links: list[str]) -> tuple[str, str]:
    """Returns (url, kind) where kind is 'homepage' | 'readme' | 'repo'."""
    if repo_meta.get("homepage"):
        return repo_meta["homepage"], "homepage"
    for url in readme_links:
        if any(pattern in url.lower() for pattern in DOCS_PATTERNS):
            return url, "readme"
    return repo_meta["html_url"], "repo"   # honest fallback — dashboard labels this "repo", not "docs"
```
README link extraction: fetch via GitHub's `GET /repos/{owner}/{repo}/readme` (returns base64-encoded content or use the `Accept: application/vnd.github.raw+json` variant for plain text), then regex/markdown-link-extract for `[text](url)` and bare URLs — no new dependency needed for this (avoid pulling in a full markdown parser for link extraction alone).

### Anti-Patterns to Avoid
- **Computing velocity inline during collection:** couples the scoring formula to the collector; store only raw `snapshots`, compute in the separate `score.py` pass (ARCHITECTURE.md Anti-Pattern 1).
- **Retrying a 403 permission-denied backfill call as if it were transient:** per D-08, retries are for *transient* failures (rate-limit, timeout); a 403 from the stargazers-restriction (Critical Finding) is permanent for that repo and must be recorded as `backfill_status='blocked'`, not endlessly retried next run.
- **Ranking on Wilson bound alone without the absolute floor:** validated above to fail the exact pitfall test case — both mechanisms are required.
- **Fetching every stargazer page "just to be safe":** defeats D-06's request cap and the entire point of *sampled* pagination; always bound backfill to the configured per-repo request cap.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry/backoff with jitter | A custom `for attempt in range(n): sleep(2**attempt)` loop | `tenacity` decorators | Easy to get subtly wrong (missing jitter, not respecting `Retry-After`, retrying non-idempotent calls) — CLAUDE.md explicitly forbids this |
| Conditional-request caching (ETag storage/lookup) | A hand-rolled dict/file mapping URL→ETag | `hishel` (RFC 9111-compliant transport wrapper for httpx) | hishel handles storage, revalidation, and the `If-None-Match`/304 dance transparently; a hand-rolled version is easy to get wrong on cache invalidation |
| Confidence-bounded ranking under small-sample noise | A custom "if count < X, penalize by Y%" heuristic | Wilson score lower bound | A well-established, well-understood closed-form solution (same one used by Reddit/HN-style ranking); an ad-hoc penalty has no principled basis and is harder to reason about or tune |
| SQLite upsert / idempotent write | Manual `SELECT` then `INSERT`/`UPDATE` branching in Python | `INSERT ... ON CONFLICT DO UPDATE` | Native to SQLite since 3.24 (2018); atomic, race-free within a single connection, and exactly matches DATA-05's requirement |
| htmx-driven partial re-render routing | Client-side JS framework/state management | Check `HX-Request` header, return a template fragment vs. full page | This is the entire reason htmx was chosen over a SPA — don't reintroduce client state to solve a problem the stack already solves |

**Key insight:** every "don't hand-roll" item above already has a library the project has already chosen; the risk in this phase is not picking the wrong tool but *skipping* the tool under time pressure and hand-rolling something that looks equivalent but is missing an edge case (jitter, cache invalidation, floor-before-ratio, atomicity).

## Common Pitfalls

(Full detail in `.planning/research/PITFALLS.md` — this section restates the ones with the most direct bearing on this phase's plan, plus the new finding from this session.)

### Pitfall 0 (new this session): Stargazer-timestamp endpoint restriction
See **Critical Finding** above. **Warning sign this wasn't handled:** every backfill attempt for a non-owned repo silently produces zero backfilled snapshots with no visible flag — exactly Pitfall 1's failure mode, applied to the backfill sub-system specifically. **Mitigation:** `backfill_status` column + distinct `'blocked'` state (not `'failed'`, which implies transient/retryable) recorded per entity, and the health header strip should be able to reflect "N of M tracked repos have real backfill history" if this becomes user-visible information worth surfacing (optional; at minimum, `run_manifest` must record it).

### Pitfall 1: Silent collector failure
A source returns HTTP 200 with an empty/near-empty payload and the daily job "succeeds" with no exception. **Mitigation already designed into D-16:** the health strip escalates on zero-items-against-trailing-average, and `run_manifest` records item counts per stage — this must be wired from the collector's very first version, not retrofitted.

### Pitfall 2/3: Small-number noise, launch-day spikes, weekday seasonality
Addressed by D-09 (7-day window, cancels weekday seasonality) + D-10 (absolute floor) + D-11 (Wilson bound) — validated numerically above. No further damping in Phase 1 per D-12; instead log the Jaccard rank-overlap stability metric each run so a real stability problem is discovered empirically:
```python
def rank_overlap(prev_top_n: set[int], curr_top_n: set[int]) -> float:
    if not prev_top_n and not curr_top_n:
        return 1.0
    return len(prev_top_n & curr_top_n) / len(prev_top_n | curr_top_n)
```

### Pitfall 8: Windows Task Scheduler wake-from-sleep (forward reference only)
**Explicitly out of scope for Phase 1** per CONTEXT.md's Phase Boundary (SCHED-01/02 are Phase 4). Noted here only because the manual `python -m techtrend.ingest` invocation in Phase 1 should still log to a file (stdlib `logging`, `FileHandler`), since that habit is what makes Phase 4's headless Task-Scheduler-driven run debuggable later — cheap to establish now, awkward to retrofit. No wake-timer/scheduler configuration work belongs in this phase.

## Code Examples

See Architecture Patterns 2–6 above for the load-bearing examples (schema DDL, upsert, Wilson scoring + validation, GitHub collector with retry/cache, FastAPI+htmx routing, docs-link resolution). Two additional snippets:

### Config loading (tomllib, stdlib)
```python
import tomllib
from pathlib import Path

with open(Path("config/tracked.toml"), "rb") as f:
    config = tomllib.load(f)

SEED_REPOS: list[str] = config["seed"]["repos"]                 # ["anthropics/claude-code", ...]
TOPICS_ALLOWLIST: list[str] = config["discovery"]["topics"]      # ["llm", "ai-agents", "mcp", ...]
KEYWORD_FALLBACK: list[str] = config["discovery"]["keywords"]
FORCE_INCLUDE: list[str] = config["overrides"]["force_include"]
FORCE_EXCLUDE: list[str] = config["overrides"]["force_exclude"]
DORMANCY_DAYS: int = config["tunables"].get("dormancy_days", 90)
BACKFILL_REQUEST_CAP: int = config["tunables"].get("backfill_request_cap", 20)
WINDOW_GAIN_FLOOR: int = config["tunables"].get("window_gain_floor", 25)
STALENESS_HOURS: int = config["tunables"].get("staleness_hours", 36)
```

### score_version bookkeeping (discretion item)
Recommend a single module-level constant, bumped manually on any formula change:
```python
# pipeline/score.py
CURRENT_SCORE_VERSION = 1  # bump whenever the formula in score_entity() changes

def rescore_all(conn):
    """Deletes and recomputes ALL rows for CURRENT_SCORE_VERSION — safe, no network I/O."""
    conn.execute("DELETE FROM scores WHERE score_version = ?", (CURRENT_SCORE_VERSION,))
    for entity in fetch_all_entities(conn):
        gained, total, window_days = compute_window_gain(conn, entity.id, days=7)
        eligible, wilson = score_entity(gained, total, floor=WINDOW_GAIN_FLOOR)
        conn.execute(
            "INSERT INTO scores (entity_id, run_date, score_version, stars_gained, window_days, "
            "wilson_lower_bound, eligible) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entity.id, today(), CURRENT_SCORE_VERSION, gained, window_days, wilson, int(eligible)),
        )
```
Old `score_version` rows are left in place (cheap, small table) rather than deleted, so a formula regression can be compared against the prior version's output if needed — this is a discretionary choice, not required by any locked decision.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sample GitHub's own `stargazers` + `star+json` endpoint for any public repo's star-timestamp history (what D-05 specifies) | That endpoint now returns 403/404 for any repo the caller isn't an admin/collaborator on | GitHub changelog, 2026-06-30, rolled out through July 2026 | **Directly breaks D-05/COLL-02 as literally written for discovery-mode repos** — see Critical Finding |
| Third-party star-history dashboards (star-history.com) fetched live per-repo star curves for any public repo | Same restriction broke these tools too; star-history.com's own blog describes charts as "broken for now" for non-owned repos | Same June/July 2026 change | Confirms this is a platform-wide change, not specific to any one client's usage pattern |
| GH Archive / OSS Insight already relied on the public Events API mirror (`WatchEvent`), not the live stargazers-listing endpoint | Unaffected by the June/July 2026 restriction — remains a viable path to real historical star data for non-owned repos | N/A — GH Archive has run since 2011 | This is the basis for Critical Finding Option B |

**Deprecated/outdated:** any research or blog post (including parts of this project's own `PITFALLS.md`/`ARCHITECTURE.md`, written 2026-07-19 but apparently just before this restriction's effects were verified in this session) that assumes the stargazers-with-timestamp endpoint is freely readable for any public repo should be treated as describing the **pre-restriction** state of the API.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The Wilson-score framing `p̂ = stars_gained_in_window / stars_total_now`, `n = stars_total_now` is a reasonable adaptation of the Wilson lower bound to a growth-rate ranking problem | Pattern 3 (Velocity Scoring) | If this framing produces poor rankings in practice (e.g., systematically over-favoring very small/new repos beyond what "genuine velocity" should reward), the formula needs revisiting — but the floor+Wilson combination has been validated against the one concrete test case CONTEXT.md specifies, so the immediate pitfall is covered even if the framing isn't provably optimal |
| A2 | GH Archive (Critical Finding Option B) is an acceptable "official enough" data source to satisfy D-05's original intent, despite D-05 explicitly rejecting third-party star-history services for being "unofficial, no SLA, rot silently" | Critical Finding | If the user judges GH Archive to carry the same rejected risk profile as star-history.com/OSS Insight, Option A (graceful degradation, no real backfill for non-owned repos) becomes the only path, and Roadmap Success Criterion #1 is met in degraded form only until ~1 week of live data accrues per entity |
| A3 | hishel's exact `CacheClient`/`SQLiteStorage` constructor signature and storage-backend list (file/redis/sqlite/S3) as presented in Pattern 4 | Pattern 4 (GitHub Collector) | This session's direct docs fetch to hishel.com was blocked (404/thin content); the API shape is corroborated via web search of hishel's GitHub repo and third-party write-ups, but exact kwargs should be confirmed against `pip show hishel` / the installed version's docstrings before relying on the literal code shown |
| A4 | `docs.github.com` "best practices" page's ETag/304-does-not-count-against-limit statement applies identically when using an authenticated fine-grained PAT (not just classic PAT/OAuth) | Pattern 4 (GitHub Collector) | Low risk — this is standard, long-documented GitHub API behavior, but token-type-specific edge cases were not separately verified this session |

**If this table is empty:** N/A — see rows above; the two most consequential are A1 (scoring formula shape) and A2 (backfill data-source decision), both of which the planner/user should explicitly confirm.

## Open Questions

1. **Does the user want Option A (graceful degradation, no new infra) or Option B (GH Archive/BigQuery) for backfill in Phase 1?**
   - What we know: Option A ships this week with zero new dependencies; Option B fully satisfies D-06's original intent but adds a GCP/BigQuery dependency not in the approved stack.
   - What's unclear: whether the user considers a GCP dependency acceptable for a "local, no-hosting, single-user" tool, or whether degraded day-one ranking (for repos not owned by the user) is acceptable given it self-heals within ~1 week of live daily runs.
   - Recommendation: default to Option A in the plan (lowest risk, ships now), explicitly flag the tradeoff to the user before/during planning rather than silently deciding.

2. **Does the seed list include any repos the owner actually owns/collaborates on (e.g., their own GSD/Superpowers repos)?**
   - What we know: those specific repos, if owned by the user, WOULD get real stargazer-timestamp backfill even under the new restriction (admin/collaborator access is exempt).
   - What's unclear: the exact seed list composition wasn't specified beyond illustrative examples in CONTEXT.md.
   - Recommendation: the collector should not assume backfill will succeed OR fail uniformly — attempt it per-repo and record the per-repo outcome (Pattern 3's `backfill_status`), which already handles this correctly regardless of the answer.

3. **Exact numeric defaults for config knobs** (dormancy=90 days, backfill request cap=20, window-gain floor=25, staleness=36h) — CONTEXT.md marks these as "Claude's Discretion, suggest X." This research adopts CONTEXT.md's suggested defaults as the recommended starting values; the planner should carry these through as config defaults, not code constants.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | ✓ | 3.13.5 | — |
| stdlib `sqlite3` | Schema/storage | ✓ | 3.49.1 (bundled) | — |
| pip | Dependency install | ✓ | 25.1.1 | — |
| `uv` | Dependency management (optional per CLAUDE.md) | ✗ | — | `pip` + `venv` (already available, CLAUDE.md lists both as acceptable) |
| git | Version control | ✓ | 2.39.1 | — |
| `fastapi`/`uvicorn`/`httpx`/`hishel`/`tenacity`/`pydantic`/`jinja2`/`python-dotenv` | Core app | ✗ (none installed yet — greenfield) | see Standard Stack table for target versions | Install step is itself a Phase 1 task, not a blocker |
| GitHub PAT (`GITHUB_TOKEN`) | Authenticated collection (COLL-07) | Unknown — not verifiable from this session | — | If absent, collector falls back to unauthenticated 60 req/hour, which CLAUDE.md/PITFALLS.md both say is unacceptable for this project; a token must be created and placed in `.env` as a Phase 1 setup task |

**Missing dependencies with no fallback:** none — every gap above has a stated fallback or is itself a planned Phase 1 setup task.
**Missing dependencies with fallback:** `uv` → `pip`+`venv`.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` (not yet installed — greenfield) |
| Config file | none — see Wave 0 |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCORE-02/03 | 2→10-star item does not outrank 4,000→4,300-star item | unit | `pytest tests/test_score.py::test_small_number_noise_excluded -x` | ❌ Wave 0 |
| SCORE-02/03 | Item below window-gain floor is excluded regardless of `p̂` | unit | `pytest tests/test_score.py::test_floor_excludes_before_wilson -x` | ❌ Wave 0 |
| SCORE-01 | Window gain computed correctly with fewer than 7 days of snapshots (day-1/partial history) | unit | `pytest tests/test_score.py::test_partial_window_gain -x` | ❌ Wave 0 |
| DATA-05/COLL-09 | Re-running collection twice for the same day does not duplicate entities or snapshots | integration | `pytest tests/test_idempotency.py::test_rerun_no_duplicate_entities -x` | ❌ Wave 0 |
| DATA-05 | Re-running a partially-failed run resumes via `run_manifest`, does not redo completed stages | integration | `pytest tests/test_idempotency.py::test_resume_skips_completed_stages -x` | ❌ Wave 0 |
| COLL-02 | Backfill 403 (blocked) is recorded as `backfill_status='blocked'`, not retried as transient | unit | `pytest tests/test_backfill.py::test_403_marks_blocked_not_retried -x` | ❌ Wave 0 |
| DASH-05 | Docs-link resolution chain falls back correctly through homepage → readme → repo, labeling honestly | unit | `pytest tests/test_docs_link.py::test_fallback_chain_labels_correctly -x` | ❌ Wave 0 |
| HEALTH-01/02 | Zero-items-from-a-source is recorded distinctly from a hard failure and flagged | unit | `pytest tests/test_health.py::test_zero_items_flagged_not_silent -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` / `pytest.ini` — pytest not yet installed or configured
- [ ] `tests/conftest.py` — shared fixtures (temp SQLite DB, sample GitHub API response fixtures — no live network calls in tests, per CLAUDE.md's stated testing philosophy)
- [ ] `tests/test_score.py`, `tests/test_idempotency.py`, `tests/test_backfill.py`, `tests/test_docs_link.py`, `tests/test_health.py` — none exist yet
- [ ] Framework install: `pip install pytest`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Single local user, no login surface in Phase 1 |
| V3 Session Management | No | No sessions — stateless read-only GET dashboard |
| V4 Access Control | No | No auth boundary to enforce; dashboard binds to localhost only |
| V5 Input Validation | Yes | `pydantic` v2 models validate every GitHub API response before it touches `entities`/`snapshots`; Jinja2's default autoescaping (do not use `|safe` on any externally-sourced field — repo names, descriptions, README-derived docs links) prevents stored XSS from a crafted repo name/description (PITFALLS.md Security Mistakes table) |
| V6 Cryptography | Minimal | No hand-rolled crypto; the only secret is `GITHUB_TOKEN`, loaded via `python-dotenv` from an untracked `.env`, never logged or rendered |
| V7 Error Handling & Logging | Yes | Ingestion log file must never write the raw `Authorization` header or token value; log GitHub error status codes/messages only |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stored XSS via a malicious/crafted GitHub repo name, description, or README-derived docs link rendered in the dashboard | Tampering | Jinja2 autoescaping (default for `.html` templates via `Jinja2Templates`); never mark externally-sourced strings `|safe` |
| Secret leakage — `GITHUB_TOKEN` committed to git or written into a log file | Information Disclosure | `.env` in `.gitignore`; `python-dotenv` loads it at runtime only; structured logging must exclude the `Authorization` header |
| Rate-limit exhaustion / "denial of wallet" via runaway polling | Denial of Service (self-inflicted) | Conditional requests (hishel ETag caching) + `tenacity` backoff + the daily-cadence design itself (no tight polling loops) |
| Treating fetched README text as trusted when extracting docs links | Tampering (low severity here — Phase 1 only extracts a URL string, does not render/execute README content, and does not yet pass it to an LLM) | Regex/pattern-match extraction only, no markdown execution; this becomes a higher-stakes concern in Phase 2 when README text is fed to the LLM (PITFALLS.md Pitfall 4/prompt-injection) — not a Phase 1 concern since there is no LLM call yet |

## Sources

### Primary (HIGH confidence — official docs, verified this session)
- [GitHub Docs: Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) — 5,000/hr authenticated core, 60/hr unauthenticated
- [GitHub Docs: Search API](https://docs.github.com/en/rest/search/search) — 30/min authenticated, 10/min unauthenticated, 1,000-result cap
- [GitHub Docs: Best practices for using the REST API](https://docs.github.com/rest/guides/best-practices-for-using-the-rest-api) — conditional requests don't count against rate limit when authenticated and a 304 is returned
- [GitHub Changelog: Upcoming access restrictions to public API endpoints and UI views (2026-06-30)](https://github.blog/changelog/2026-06-30-upcoming-access-restrictions-to-public-api-endpoints-and-ui-views/) — the Critical Finding
- [sqlite.org: The ON CONFLICT Clause](https://sqlite.org/lang_conflict.html) — UPSERT syntax, available since 3.24.0
- PyPI registry direct lookups (`pip index versions`) for fastapi, uvicorn, jinja2, httpx, hishel, tenacity, pydantic, python-dotenv, feedparser — all confirmed present/current this session

### Secondary (MEDIUM confidence — cross-corroborated web sources)
- [star-history.com: GitHub Has Restricted Access to Star Data](https://www.star-history.com/blog/github-stargazer-api-restriction/) — independent confirmation of the Critical Finding's impact
- [GH Archive](https://www.gharchive.org/) and [igrigorik/gharchive.org](https://github.com/igrigorik/gharchive.org) — backfill Option B basis
- [OSS Insight docs](https://ossinsight.io/docs/about) — confirms GH Archive as its own underlying data source
- Wilson score interval implementations (multiple independent gists/explainers, cross-corroborated) — formula shape confirmed, framing (A1) is this researcher's adaptation
- [hishel.com](https://hishel.com/), [github.com/karpetrosyan/hishel](https://github.com/karpetrosyan/hishel) — storage backends and CacheClient/CacheTransport pattern existence confirmed; exact constructor kwargs not independently fetched this session (see Assumption A3)
- [tenacity.readthedocs.io](https://tenacity.readthedocs.io/en/latest/) — retry/backoff decorator pattern
- FastAPI+htmx integration write-ups (blakecrosley.com, testdriven.io, dev.to — cross-corroborated) — HX-Request header check + partial-render pattern

### Tertiary (LOW confidence — general/training knowledge, not independently re-verified this session)
- SQLite WAL + `check_same_thread`/connection-per-request concurrency guidance — well-established pattern, cross-corroborated across several web sources this session, but no single canonical source
- README link-extraction approach for docs-link resolution (Pattern 6) — this researcher's proposed implementation, not sourced from a published reference

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version verified directly against the live PyPI registry this session
- GitHub API mechanics (rate limits, conditional requests, the stargazers restriction): HIGH — verified against official GitHub docs and changelog, cross-corroborated by an independent affected third party (star-history.com)
- Scoring formula (Wilson + floor): HIGH on the math itself (hand-computed and checked against the exact pitfall test case); MEDIUM on the specific `p̂`/`n` framing being the *best* choice (flagged as Assumption A1)
- Architecture/project structure: HIGH — directly translates the project's own already-researched ARCHITECTURE.md, only the language-specific syntax changed
- FastAPI+htmx wiring: MEDIUM — pattern well-corroborated across multiple sources, but not fetched from a single canonical/official doc
- hishel exact API surface: MEDIUM — existence and shape confirmed, exact kwargs not independently verified (docs.hishel.com fetch was blocked this session)

**Research date:** 2026-07-19
**Valid until:** ~30 days for the general architecture/scoring guidance; **re-verify the stargazers-restriction status immediately before implementing COLL-02** since this is an active, recently-rolled-out platform change that could still evolve (grandfathering, appeals process, or reversal are all plausible given it broke third-party tools GitHub may want to keep functioning).
