# Phase 1: Foundation & First Signal — GitHub, Scored and Visible - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the thinnest end-to-end vertical slice that is actually useful: SQLite schema (`entities`, `snapshots`, `scores`, `run_manifest`), a single GitHub collector implementing the plugin interface, a backfill that makes velocity meaningful on run #1, a confidence-bounded velocity scorer, and a minimal read-only FastAPI/Jinja2/htmx dashboard showing a ranked list with source + docs links and a visible health/freshness indicator.

**Explicitly NOT in this phase:**
- No LLM calls, no summaries, no section taxonomy, no section filtering (Phase 2 — DASH-02, ENR-*)
- No Hacker News, npm, PyPI, or RSS collectors (Phase 3 — COLL-03/04/05)
- No Windows Task Scheduler wiring (Phase 4 — SCHED-01/02)
- No cross-source entity resolution (deferred to v2; entities key strictly on `(source, source_native_id)`)

</domain>

<decisions>
## Implementation Decisions

### Tracked Repo Universe

- **D-01:** Repos enter the tracked set two ways: a hand-written **seed list** of repos the owner already cares about (Claude Code, GSD, Superpowers, Guardrails AI, Aider, etc.) **plus** a daily **GitHub search** over AI-coding topics/keywords that can promote newly-found repos into the set. Discovery is a first-class requirement, not just velocity tracking of a known list.

- **D-02:** Tracking is **sticky with quiet retirement**. Once a repo is admitted it is snapshotted every day thereafter regardless of whether it still appears in search results — this is required for velocity continuity, since gaps in the snapshot series break the delta math. A repo showing no meaningful star movement over a long window (suggest 90 days; make it config) is marked **dormant** and stops being polled, but its history is retained and it can wake back up. Rationale: keeps the snapshot series continuous while bounding rate-limit usage over time.

- **D-03:** Relevance filtering for discovered repos is **fully deterministic** (Phase 1 has no LLM available). Admit a search hit if it carries any topic from a curated **topics allowlist** (`llm`, `ai-agents`, `mcp`, `rag`, `agentic`, `code-generation`, …) **OR** if its name/description matches a **keyword list**. The keyword fallback exists specifically to catch brand-new repos that have not tagged themselves yet — which are exactly the highest-value discoveries. Both lists live in config and are editable without a code change.

- **D-04:** Escape hatch is a **config force-include allowlist + force-exclude blocklist**. Force-include pins a repo into the tracked set regardless of topic/keyword match; force-exclude permanently banishes a repo and suppresses it from future discovery. These live in the same config file as the seed list. The dashboard stays strictly read-only — per ARCHITECTURE.md the dashboard never invokes a pipeline stage — so all curation happens in config, never in the UI.

### Day-One Star History (Backfill)

- **D-05:** Backfill uses **sampled stargazer pagination** against GitHub's own API — the `stargazers` endpoint with the `application/vnd.github.star+json` Accept header returns `starred_at` timestamps. Do **not** fetch every page; binary-search / sample pages to establish the recent slope. No third-party dependency (star-history.com, OSS Insight) — those are unofficial, have no SLA, rot silently (PITFALLS.md #1), and would become a second source of truth alongside our own snapshots.

- **D-06:** Reconstruct **~90 days** of star accrual per repo, with a **hard per-repo request cap** (suggest ~20 stargazer page requests; make it config). 90 days gives enough baseline to judge whether current growth is unusual *for that repo* — the spike-vs-trend distinction from PITFALLS.md #3 — while 30 days would not. If a repo is too large to resolve within the cap, accept a coarser curve rather than blowing the rate-limit budget.

- **D-07:** Backfilled points are written into the **same `snapshots` table** with the derived historical date as `collected_at`, plus a **`source_kind` provenance column** distinguishing `'backfill'` from `'observed'`. The scorer then reads one uniform series with no special-casing. The provenance flag keeps estimates auditable and allows surgically purging/redoing a bad backfill without touching real observations. The existing `UNIQUE(entity_id, collected_at, metric_name)` constraint makes re-running the backfill idempotent for free (DATA-05).

- **D-08:** Backfill triggers **on first sight** — the first run a repo is admitted to the tracked set. Per-repo completion is recorded (e.g. a `backfilled_at` column on the entity); a repo whose backfill failed or was truncated by the request cap is **retried on the next run** rather than being silently left with a stub history. Live daily snapshotting begins immediately regardless — **backfill failure must never block current data collection**.

- **D-08a (added post-research, supersedes the reachability assumption in D-05/D-06):** RESEARCH.md's Critical Finding established that GitHub restricted the `stargazers`-with-`starred_at` endpoint to a repo's own admins/collaborators (changelog late June/July 2026), so the D-05 mechanism returns `403 Forbidden` for essentially every repo this dashboard tracks. **Decision: Option A — graceful degradation.** The collector still *attempts* sampled stargazer pagination exactly as D-05 specifies (it succeeds for any repo the operator owns or collaborates on), and on `403` records a documented degraded state for that repo rather than failing the run. Consequently **COLL-02 / D-05 / D-06 are satisfied in degraded form only** for non-owned repos — plans and verification must state this explicitly and must not claim full satisfaction as originally written.

  Accepted consequence: an entity with no backfill has `window_days=1` on day one and will almost always fall below the D-10 star-gained floor, so it is honestly excluded rather than falsely ranked. **The dashboard is expected to be sparse for roughly the first week** until live observed snapshots accrue. This is intended behavior, not a defect — the empty/sparse state must read as "still gathering data", not as a failure.

  **Option B (GH Archive / BigQuery `WatchEvent` mirror) is explicitly deferred, not rejected.** It is unaffected by the restriction and is the only path that fully satisfies D-06's original intent, but it adds a GCP/BigQuery dependency outside the approved stack, and RESEARCH.md Assumption A2 flags that it may carry the same third-party-source risk profile D-05 rejected. Revisit as a fast-follow once the real sparseness of the degraded dashboard is observed.

### Ranking Formula

- **D-09:** Velocity is computed over a **7-day trailing window**. A full week naturally cancels day-of-week seasonality (PITFALLS.md #3) with no explicit weekday normalization needed, while staying responsive enough that a genuine surge surfaces within days. (14-day was considered and rejected as too laggy for a daily-habit tool; a dual 7d/14d window was considered and deferred as premature complexity for the first scoring implementation.)

- **D-10:** The SCORE-03 absolute floor is on **stars gained within the window**, not on total star count. A repo must have gained at least N stars in the trailing 7 days (suggest N=25; make it config) to be eligible to rank at all, regardless of size or percentage growth. Rationale: gating on recent movement keeps a brand-new repo that genuinely took off eligible immediately, whereas a total-count floor would systematically exclude exactly the fresh signal this dashboard exists to catch. A 3→12-star repo still fails to qualify.

- **D-11:** Scoring uses a **Wilson-style lower confidence bound** (SCORE-02) so low-sample items are pulled toward zero rather than exploding on percentage growth.

- **D-12:** **No additional damping in Phase 1.** The 7-day window plus the Wilson bound may well satisfy SCORE-05 on their own. Ship that, and **log a stability metric** each run (e.g. rank-overlap / Jaccard between consecutive runs' top-N) so the need for further smoothing is discovered empirically rather than guessed. EWMA smoothing was rejected as risking a dashboard that is stable because it barely responds. Rank hysteresis was rejected specifically because it introduces order-dependent state — the displayed rank would depend on yesterday's rank, breaking the "scores are a pure function of `(entities, snapshots)`" property that makes re-scoring free (ARCHITECTURE.md, DATA-03).

- **D-13:** For SCORE-04 (cross-source normalization) — **build the seam, calibrate later**. Structure the scorer so the source-specific step (raw metric → comparable momentum value) is distinct from the source-agnostic ranking step, and have GitHub implement it. The normalization boundary exists and is proven with one source; Phase 3 adds HN/npm/PyPI by implementing that step, not by restructuring the scorer. Do **not** attempt to calibrate against HN points or download counts that have never been observed.

### Dashboard & Health Display

- **D-14:** The dashboard is a **dense sortable table** — one row per repo: rank, name, velocity score, stars gained in window, total stars, source link, docs link. Sorting via htmx GET returning an HTML partial (DASH-03). Chosen for scannability at 50+ items, matching the "five minutes, know what's new" core value. Phase 2 can hang section filters off this layout without a redesign. Cards were rejected (poor scan density, and Phase 1 has no summary text to justify the whitespace); sparklines were deferred despite the 90-day backfill making them feasible.

- **D-15:** Docs-link resolution (DASH-05) is a **deterministic fallback chain**: GitHub `homepage` field → scan README for a link whose text or URL matches docs patterns (`docs.`, `/docs`, "documentation", "getting started") → fall back to the repo URL itself, **labeled honestly as "repo" rather than "docs"**. Degrades visibly instead of silently pointing somewhere wrong.

- **D-16:** Health/freshness is a **persistent header strip that escalates** (DASH-06, HEALTH-02). Always visible at the top of the page showing "last successful run" as a relative time. Quiet grey text in the normal case; escalates to a loud warning banner when the last run is stale (>36h), when a collector reported failure, or when GitHub returned zero items against a non-trivial trailing average (the floor check from PITFALLS.md #1). One always-present surface — and Phase 4's missed-run indicator comes for free. A dedicated `/health` page over `run_manifest` was deferred; the data is in the DB regardless.

- **D-17:** The dashboard is **started manually** (`uvicorn app:app`) in Phase 1 — Phase 4 adds an at-logon trigger, so no startup machinery here. With no data yet, the table renders an **explicit empty state** ("No run has completed yet — run `python -m techtrend.ingest`") rather than a blank table, so a first run is self-explanatory instead of looking broken. The dashboard must **never** trigger a pipeline run on page load — that would break the pure-downstream-reader rule that makes the dashboard safe to reload.

### Claude's Discretion

The user deferred to recommendations throughout; these were consistently the recommended options, so treat them as decided rather than as open discretion. Genuinely open for the researcher/planner to settle:

- Exact numeric values for the config knobs (dormancy threshold, per-repo request cap, window-gain floor, staleness threshold) — the *shape* is decided above; sensible defaults are Claude's call, but every one of them must be **config, not a code constant**.
- The specific sampling algorithm for stargazer pagination (binary search vs. fixed stride vs. adaptive).
- Config file format and location (the stack section favors `python-dotenv` for secrets; the tunables/seed/allowlist/blocklist config is a separate, non-secret file).
- Where `score_version` bookkeeping lives and how a formula change triggers a re-score.
- How release events (COLL-01) are represented alongside stars — whether as a second metric in `snapshots` or as their own concern.
- Testing approach — PITFALLS.md gives two concrete assertions worth encoding as tests: a synthetic 2→10-star item must not outrank a synthetic 4,000→4,300-star item, and re-running a collection must not duplicate entities or snapshots.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope and requirements
- `.claude/CLAUDE.md` — **Locked tech stack** (Python 3.12/3.13, SQLite + WAL, FastAPI/Jinja2/htmx, httpx + hishel + tenacity, `anthropic` SDK, ruff/pytest/uv), plus the What-NOT-to-Use table. The stack is decided; do not re-litigate it.
- `.planning/PROJECT.md` — Core value, the three signal types (releases/traction/discourse), the seven-section taxonomy (Phase 2), constraints, and Key Decisions.
- `.planning/REQUIREMENTS.md` — The 22 requirement IDs this phase must satisfy (listed below), plus the v2/Out-of-Scope lists that bound scope creep.
- `.planning/ROADMAP.md` §"Phase 1" — Phase goal and the five success criteria that define done.

### Architecture and design (load-bearing for this phase)
- `.planning/research/ARCHITECTURE.md` — **The most important ref for this phase.** Defines the table shape (`entities` / `snapshots` / `scores` / `enrichments` / `run_manifest`), the five real seams, the collector plugin interface + registry pattern, the append-only-snapshot / derived-score separation, the idempotency mechanisms table, and the recommended project structure. §"Build Order" steps 1–4 are precisely this phase.
- `.planning/research/ARCHITECTURE.md` §"Deliberate simplification" — Entities key strictly on `(source, source_native_id)`; **no cross-source entity resolution in v1**.
- `.planning/research/PITFALLS.md` — **Required reading.** Pitfall #1 (silent collector failure — drives D-16's floor check and the per-source health log, HEALTH-01/02), Pitfall #2 (small-number noise and fake stars — drives D-10/D-11), Pitfall #3 (launch-day spikes and weekday seasonality — drives D-09). Also the "Looks Done But Isn't" checklist and the Integration Gotchas table (GitHub rate limits, ETag conditional requests).
- `.planning/research/STACK.md` — Library-level detail behind the CLAUDE.md stack summary.
- `.planning/research/FEATURES.md`, `.planning/research/SUMMARY.md` — Supporting research context.

### External API references (verify at implementation time)
- GitHub REST API — rate limits (5,000/hr authenticated core; Search API is a **separate, much stricter** ~30/min budget), conditional requests via `ETag`/`If-None-Match` (COLL-07, COLL-08), and the `application/vnd.github.star+json` Accept header for `starred_at` timestamps (D-05).

### Requirements owned by this phase
DATA-01, DATA-02, DATA-03, DATA-05, COLL-01, COLL-02, COLL-06, COLL-07, COLL-08, COLL-09, SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05, DASH-01, DASH-03, DASH-04, DASH-05, DASH-06, HEALTH-01, HEALTH-02

</canonical_refs>

<code_context>
## Existing Code Insights

**Greenfield.** The repository contains only `.planning/` and `.claude/` — no source code, no dependency manifest, no test suite exists yet. There are no codebase maps in `.planning/codebase/`.

### Reusable Assets
- None. Phase 1 establishes every pattern from scratch.

### Established Patterns
- None in code. The binding constraints come from documents rather than existing code: the locked stack in `.claude/CLAUDE.md` and the architecture in `.planning/research/ARCHITECTURE.md` §"Recommended Project Structure" (note: that structure is written in TypeScript notation as illustrative pseudocode — translate the *shape* to Python module layout, not the syntax).

### Integration Points
- This phase creates the integration points every later phase depends on:
  - The **collector plugin interface + registry** — Phase 3's success criterion is that adding three sources touches only new collector modules plus one registry entry.
  - The **`scores` table and gate seam** — Phase 2 reads `scores` to decide what reaches the LLM.
  - The **health/freshness header strip** — Phase 4 reuses it as the missed-run indicator.
  - The **per-source normalization step** (D-13) — Phase 3's sources plug in here.

</code_context>

<specifics>
## Specific Ideas

- **Seed list starting points** — PROJECT.md names the owner's actual interests: Claude Code, GSD, Superpowers, Guardrails AI. ARCHITECTURE.md and the taxonomy suggest others (Cursor, Codex, Aider, LangGraph, CrewAI, Ollama, llama.cpp). The seed list should be populated with the owner's genuine watchlist, not a generic "popular AI repos" list.
- **Honest labeling over silent wrongness** — this preference showed up twice independently: the docs link falls back to a link labeled "repo" rather than pretending to be docs (D-15), and the empty dashboard says why it's empty rather than rendering zero rows (D-17). Apply the same instinct elsewhere in the phase.
- **Measure before optimizing** — the stability question (D-12) was resolved by shipping the simple thing plus a metric rather than pre-building damping. Prefer that pattern where a knob's necessity is unproven.

</specifics>

<deferred>
## Deferred Ideas

- **Sparklines in the dashboard table** — inline SVG star-history per row. The 90-day backfill makes this feasible for free, and it would show spike-vs-trend at a glance. Deferred from Phase 1 as extra build in a phase about proving the pipeline. Good candidate for a later polish pass.
- **Dedicated `/health` page** — full per-source run history rendered from `run_manifest`. The data is being written regardless (HEALTH-01), so this is purely a view that can be added whenever it's actually wanted.
- **Dual 7d/14d window with spike detection** — rank on the 7-day slope, use the 14-day slope to break ties and damp items whose windows disagree sharply. Directly encodes spike-vs-trend. Revisit if D-12's stability metric shows the single window is insufficient.
- **EWMA smoothing / rank hysteresis** — explicitly rejected for Phase 1 (see D-12). Hysteresis in particular should stay rejected unless the score-purity tradeoff is reconsidered.

</deferred>

---

*Phase: 1-Foundation & First Signal — GitHub, Scored and Visible*
*Context gathered: 2026-07-19*
