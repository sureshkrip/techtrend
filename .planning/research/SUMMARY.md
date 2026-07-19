# Project Research Summary

**Project:** TechTrend
**Domain:** Personal, locally-run AI/LLM ecosystem trend-tracking dashboard (ETL-style ingestion, confidence-aware velocity ranking, LLM enrichment, single-user web dashboard, daily batch, Windows 11)
**Researched:** 2026-07-19
**Confidence:** MEDIUM-HIGH

## Executive Summary

TechTrend is a single-user ETL-plus-dashboard system, not a SaaS product: a daily batch job collects from multiple heterogeneous sources (GitHub, HN, npm/PyPI, vendor changelogs, RSS), resolves each raw record to a stable entity, stores an append-only time series of metrics, derives a velocity score, gates a small subset through an LLM for summarization/classification, and serves a read-only dashboard. Experts building this kind of system converge on a small set of well-established techniques that apply directly here: separate raw observations from derived scores so re-scoring is free; use a confidence-bounded ranking formula (Wilson-lower-bound style) with an absolute floor rather than raw percentage deltas; gate LLM spend deterministically before summarization; and decouple enrichment from ingestion so an LLM outage or cost spike never blocks fresh data from landing.

The recommended approach is a single-language Python stack (FastAPI + Jinja2 + htmx, SQLite, `anthropic` SDK, `httpx`/`hishel`/`tenacity`), an entity/snapshot/score/enrichment schema with idempotency built in via unique constraints and a run-manifest, and a build order that proves the thinnest vertical slice (one collector, identity-resolve, snapshot, naive score, minimal dashboard) before adding a second source or any LLM cost. Notably, the ranking, features, and pitfalls research independently arrived at the same conclusion for the velocity formula (confidence-bounded, floor-gated, multi-day-windowed) and the same conclusion for idempotency/caching (unique keys plus content-hash caching, no message queue needed at this scale) — this convergence is treated as high-confidence, load-bearing design.

The main risks are: (1) the "day-one has no velocity" cold-start problem, which research resolves — GitHub and npm/PyPI expose retroactive historical data so those sources can rank from day 1, while HN genuinely needs two snapshots; (2) fake/gamed GitHub stars and small-number noise, both solved by the same confidence-bound-plus-floor mechanism; (3) silent collector failure and Windows Task Scheduler's unreliable wake-from-sleep behavior, both cheap to instrument now and expensive to diagnose later if skipped; and (4) several genuinely open external-dependency questions (Reddit API terms, GitHub Search API limits, GitHub Trending having no official API) that should be treated as spikes/risks during planning rather than assumed away.

## Key Findings

### Recommended Stack

Python 3.12/3.13 end-to-end (ingestion, ranking, LLM calls, web server) — single language for a solo dev, mature HTTP/feed ecosystem, official `anthropic` SDK, and a workable Windows scheduling story that Node lacks. SQLite (stdlib `sqlite3`, WAL mode) for storage — zero-ops, file-based, handles the write-then-read-heavy daily batch with no contention. FastAPI + Jinja2 + htmx for the dashboard — server-rendered, no build step, no SPA, since the actual interaction ("browse, sort, filter, click through") doesn't need client-side state. Windows Task Scheduler (not cron, not Celery) fires the daily ingestion script — the OS-native answer with zero extra infrastructure.

**Core technologies:**
- Python 3.12/3.13 — single-language runtime for ingestion, ranking, LLM calls, and web server
- SQLite (stdlib, WAL mode) — zero-ops embedded storage for entities/snapshots/scores/enrichments
- FastAPI + Jinja2 + htmx — server-rendered dashboard, no build pipeline, fits "browse/sort/filter/click-through" exactly
- Windows Task Scheduler — native daily trigger; decoupled ingestion script plus separate on-demand dashboard process is the recommended default over one always-on process
- `anthropic` SDK (Haiku 4.5 as default model tier) — structured outputs for summarize+classify; cheapest model that clears the quality bar, upgradeable per-call if classification accuracy proves poor
- `httpx` + `hishel` + `tenacity` — async-capable HTTP with RFC 9111 conditional-request caching and declarative retry/backoff

### Expected Features

The product's entire thesis — rank by velocity, not absolute popularity — has textbook solutions (HN gravity-decay, Reddit log-vote-plus-linear-time, Wilson score lower bound) that directly address the two failure modes named in PROJECT.md: small-number noise (2 to 10 stars) and dead-giant suppression (40k-star repo with no growth). GitHub Trending's actual algorithm is unpublished/opaque (LOW confidence on any "exact formula" claim) — use it only as directional inspiration (window-based, ratio-to-own-baseline), not as a spec to copy; OSS Insight's public composite formula (stars + forks + base) validates that a weighted composite, not pure velocity, is standard practice. Deduplication should be entity-anchored (canonical key: repo URL, package name, or release tag) as the cheap, precise default; embedding-similarity fallback is a v1.x add for discourse items without a shared identifier, not a v1 requirement.

**Must have (table stakes):**
- Multi-source ingestion with per-source adapters (GitHub + HN first)
- Deduplication/identity resolution before ranking (same release must not count 3x)
- Confidence-bounded, floor-gated velocity ranking (the core thesis)
- Read/unread state — without it the dashboard becomes unusable noise within a week
- Deterministic pre-ranking gate before any LLM call (cost control)
- Click-through to source plus link to official docs
- Daily scheduled run, no manual refresh

**Should have (competitive differentiators):**
- Cross-source percentile normalization (the actual "better than GitHub Trending" claim — without it this is just "GitHub Trending plus some RSS")
- Cross-source corroboration display ("seen on: GitHub + HN + changelog") — nearly free once dedup exists, and is itself a traction signal
- Backfilled history on day 1 for backfill-capable sources — removes the "wait a week to be useful" tax

**Defer (v2+):**
- npm/PyPI, vendor changelogs, Reddit sources (add after the core two-source pipeline is proven)
- Embedding-similarity dedup fallback, mute (source/section), "days consecutively ranked" counter
- Per-section decay windows, arXiv/Product Hunt/awesome-lists sources, any formal trend-lifecycle state machine (explicitly an anti-feature)

### Architecture Approach

The pipeline decomposes into seven seams: collect, normalize, identity-resolve, snapshot, score, gate, enrich, serve. The two structurally important corrections research made to the naive collect-normalize-dedupe-snapshot-score-enrich-serve framing: (1) "dedupe" is really **identity resolution** — deciding whether a raw record is a new entity or a new observation of one already tracked — and must happen before the snapshot write, since snapshots need a stable entity_id; (2) there is an explicit **gate** seam between score and enrich (a pure, cheap, synchronous threshold check) that deserves to be named separately from "enrich" because it's the only place LLM spend is decided.

**Major components:**
1. Collectors (one per source, shared interface + registry) — source-specific fetch/normalize; orchestrator never branches on source
2. Identity Resolver + Snapshot Writer — match-or-create entity, then write immutable time-series rows keyed by (entity_id, collected_at, metric_name)
3. Scorer — pure function of (entities, snapshots), no network I/O, fully replayable; writes to a separately replaceable scores table
4. Gate + Enricher — deterministic threshold check, then cache-gated (content-hash keyed) LLM summarize+classify
5. Orchestrator — drives daily run order, records per-stage success/failure in run_manifest for idempotent resume
6. Dashboard (serve) — pure read-only reader of entities/scores/enrichments; never triggers a pipeline stage

### Critical Pitfalls

1. **Silent collector failure** (the number-one killer) — a source returning 200 OK with an empty/malformed payload never throws; requires a per-source health log with a floor-check (item count vs. trailing average), independent of the item store, built in from day one.
2. **Small-number noise plus fake-star gaming** — raw percentage deltas let a 2-to-10-star repo outrank a 4,000-to-4,300-star repo, and velocity is the exact metric GitHub star-farming campaigns target (documented ~6M suspected fake stars, 2024/2025 research). Fixed by the same mechanism as the Features recommendation: Wilson-style confidence-bound ranking plus an absolute minimum-count floor.
3. **Launch-day spikes / weekend seasonality** — single-day deltas whipsaw the dashboard; use a multi-day trailing window/decay rather than yesterday-vs-today, solved together with pitfall 2 (same ranking-formula decision).
4. **LLM hallucination on brand-new tools** — the exact items this dashboard exists to surface are the ones the LLM has no reliable parametric knowledge of; always ground summarization in freshly fetched source text (README/changelog/thread), never let the model summarize "from what it knows."
5. **Windows Task Scheduler silently fails to run** — sleep/wake settings default to failure (wake timers, "wake to run," "run if missed" are all off by default); must be explicitly configured, and a "last successful run" indicator on the dashboard doubles as the user-facing health check.

## Implications for Roadmap

Architecture's proposed build order and Features' MVP definition converge strongly; the reconciled order below follows dependency order (schema, one source, score, visible dashboard, LLM cost, breadth, scheduler), matching both researchers' "thinnest vertical slice first" recommendation, with pitfall-prevention work folded into the phase where each pitfall's root cause lives rather than bolted on afterward.

### Phase 1: Schema + Data Model
**Rationale:** Every other component reads/writes this contract; nothing else, not even a "fake" collector, can be meaningfully built without entities, snapshots, scores, enrichments, and run_manifest existing first.
**Delivers:** SQLite schema with WAL mode, unique constraints (entity_id + collected_at + metric_name; entity_id + content_hash), and the run_manifest idempotency table.
**Addresses:** Architecture's "data model seam" (entity/snapshot/score/enrichment separation) — the load-bearing decision for the whole system.
**Avoids:** Computing velocity inline during collection (couples the scoring formula to collection code, destroys the audit trail) — schema enforces the append-only/derived separation from the start.

### Phase 2: First Collector — GitHub (with backfill)
**Rationale:** GitHub is backfill-capable (stargazer-timestamp pagination reconstructs full star history in one pass) — this resolves the cold-start problem for the highest-value source and means the dashboard can show real velocity, not a placeholder, from day 1. Sequencing GitHub before HN is the direct sequencing implication of the cold-start resolution — wire the backfill-capable source before the snapshot-only source.
**Delivers:** GitHub collector implementing the shared Collector interface (fetch stargazer history + Releases API), authenticated (never unauthenticated — 60 req/hour ceiling is a hard no), identity-resolve, snapshot write.
**Addresses:** the "backfilled history on day 1" differentiator.
**Avoids:** Silent collector failure — build the per-source health log and floor-check as part of the collector contract in this phase, not retrofitted; the authentication gotcha (always use a PAT).

### Phase 3: Scorer — Confidence-Bounded Velocity Ranking
**Rationale:** Score is a pure function of (entities, snapshots), independently replayable; building it standalone before the dashboard proves the ranking math in isolation. This is where the cross-cutting convergence (Wilson-lower-bound plus floor recommendation, identical fix for fake-star gaming and small-number noise) gets implemented as one decision, not two.
**Delivers:** Velocity scoring with per-source absolute floor, ratio-to-own-baseline, multi-day trailing window (not single-day delta), score_version column for auditable formula changes.
**Implements:** the "Append-Only Snapshot + Derived Score Separation" pattern.
**Avoids:** Small-number noise / fake stars, and launch-day spikes / seasonality — both are the same underlying design decision (window size + confidence penalty) and must be solved together here, not patched on after a naive delta implementation ships.

### Phase 4: Minimal Dashboard (no LLM)
**Rationale:** The thinnest end-to-end vertical slice that proves the concept — one source, real backfilled data, something ranked and visible — requires zero LLM involvement and is the right point to validate before spending any LLM budget.
**Delivers:** Read-only list view over entities and scores, sorted by velocity, linking to source; "last successful run" / collector-health indicator surfaced here (cheap now, expensive to retrofit later).
**Addresses:** the table-stakes "local web dashboard: browse, sort, click through."
**Avoids:** the staleness-invisibility failure mode — the health indicator doubles as the user-facing signal for both silent collector failure and missed scheduled runs.

### Phase 5: Gate + LLM Enrichment
**Rationale:** Cost control is explicitly a deterministic-threshold decision, not a code path — it can only be added once real scores exist to threshold against (Phase 3) and there's something to enrich (Phase 2/4).
**Delivers:** Deterministic threshold gate, LLM summarize+classify into the 7 fixed sections, content-hash-keyed enrichment cache, hard per-run item cap (independent second gate against cost spikes on viral days), grounding-on-fetched-text prompt design, temperature=0 for classification.
**Addresses:** the "two-line what/why summary" and "section classification" table-stakes.
**Avoids:** LLM hallucination on new tools (ground every prompt in fetched source text), classification drift (cache by content hash, temperature 0), and LLM cost creep on viral days (hard per-run cap alongside the threshold).

### Phase 6: Second/Third Collector — Hacker News, then npm/PyPI or changelogs
**Rationale:** This is the real test of the plugin seam — adding sources should touch only collectors/ and the registry. HN is added here (not Phase 2) because it is snapshot-only (no backfill), so it exercises the 2-snapshot cold-start fallback cleanly isolated from the backfill-capable path already proven in Phase 2.
**Delivers:** HN Algolia collector; validate that no pipeline/scorer/gate/enricher/dashboard code needed to change to add it. If it did, the Phase 2 interface boundary was drawn wrong and should be fixed here before adding more sources.
**Addresses:** the "Discourse" signal type and multi-source ingestion table stakes.
**Avoids:** Scope creep — apply the taxonomy "one obvious home" admission test explicitly when adding this and subsequent sources, before the temptation of a convenient exception arrives.

### Phase 7: Scheduler Wiring
**Rationale:** By this point idempotency is already a property of the schema and stages (Phases 1-3), not something the scheduler adds — wiring the daily trigger is deliberately last and lowest-risk.
**Delivers:** Windows Task Scheduler task with all three wake-related settings explicitly configured (wake the computer, allow wake timers, run-if-missed), decoupled from the on-demand dashboard process.
**Avoids:** Windows Task Scheduler silently failing to run — this is the phase where its full prevention checklist is executed, not assumed.

### Phase Ordering Rationale

- Schema-first is non-negotiable — nothing else can be meaningfully built without the entity/snapshot/score/enrichment contract existing.
- GitHub before HN is the direct sequencing implication of the cold-start resolution: backfill-capable sources (GitHub, npm/PyPI) can rank meaningfully from day 1, while HN genuinely needs two snapshots — wiring the backfill-capable source first means the dashboard is useful immediately rather than after a multi-day wait.
- Scorer and dashboard come before any LLM involvement so the hardest structural bets (plugin boundary shape, snapshot/score separation, something-renders-in-a-browser) are proven before spending LLM budget.
- LLM gate/enrichment is deliberately its own phase, not folded into ingestion, because cost control, failure isolation, and caching are all impossible to retrofit cleanly onto a coupled design.
- Scheduler is last because by then idempotency is already a schema/stage property, not something the scheduler needs to provide.

### Research Flags

Needs research during phase planning:
- **Phase 2 (GitHub collector):** GitHub Search API current rate limits and stargazer-timestamp-endpoint pagination mechanics should be re-verified at implementation time; GitHub Trending has no official API at all — if it's ever added as a source, it requires a scraping approach with fixture/schema tests, treat as a spike, not a standard integration.
- **Phase 6 (HN then additional sources):** Reddit API terms (pricing, Nov 2025 "Responsible Builder Policy," commercial-use restrictions) should be confirmed as current before Reddit is wired in as anything beyond a deferred/supplementary source.
- **Phase 3 (Scorer):** the exact floor constants and window sizes per source type are design choices without a single canonical answer — worth a short spike/validation pass against real data rather than guessing values upfront.

Phases with standard, well-documented patterns (skip deep research):
- **Phase 1 (Schema):** standard time-series/entity-snapshot-score schema design, cross-corroborated across multiple official vendor docs and idempotent-pipeline literature.
- **Phase 4 (Minimal dashboard):** FastAPI + Jinja2 + htmx server-rendered list view is a well-trodden pattern with no novel integration risk.
- **Phase 7 (Scheduler):** Windows Task Scheduler configuration is fully documented (if inconsistently reliable) — the fix is three known settings, not a research problem.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH / MEDIUM | Language/storage/scheduling/HTTP library choices verified against current package registries and official docs (HIGH); exact micro-versions of fast-moving web libraries (FastAPI, uvicorn) should be re-pinned at install time (MEDIUM) |
| Features | MEDIUM-HIGH | Ranking-formula math (HN/Reddit/Wilson score) is HIGH confidence — textbook, decades of production use, cross-checked across independent sources; GitHub Trending's exact algorithm and Techmeme's clustering approach are LOW confidence speculation since neither publishes internals; cold-start and dedup technique recommendations are MEDIUM |
| Architecture | MEDIUM | General ETL/data-pipeline and idempotent-pipeline patterns are well-established and cross-corroborated (treat overall shape as HIGH); no single authoritative "trend dashboard" reference architecture exists, so specific scale-down judgment calls are this project's reasoned application of general patterns |
| Pitfalls | MEDIUM-HIGH | Rate limits and API mechanics verified against official docs (HIGH); fake-star research is peer-reviewed/HIGH confidence; Windows Task Scheduler wake-reliability and LLM hallucination-on-new-entities are MEDIUM (consistent community/literature reporting, not project-specific field data) |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **GitHub Trending has no official API** — if this source is ever pursued, it requires HTML scraping with fixture/schema tests from day one; treat any addition of this source as a spike requiring its own risk assessment, not a standard collector addition.
- **Reddit API terms are a moving target** (2023+ pricing changes, Nov 2025 policy) — confirm current terms before Reddit moves from "deferred/supplementary" to "load-bearing source" in any future phase.
- **GitHub Search API's exact current rate limits** should be re-verified at Phase 2 implementation time rather than assumed from this research pass, given how frequently GitHub has changed these limits.
- **Exact floor constants and trailing-window sizes per source type** are design recommendations synthesized from general ranking literature, not empirically validated against this project's actual data — expect to tune these once real snapshot data accumulates.
- **Cross-source entity resolution is deliberately deferred** — v1 keys entities strictly on (source, source_native_id), so the same tool tracked via both GitHub and npm will appear as two separate dashboard entries. This is a known, accepted v1 simplification, not an oversight — revisit only if duplicate entries prove to be a real usability problem in practice.

## Sources

### Primary (HIGH confidence)
- GitHub Docs: Rate limits for the REST API, Best practices for using the REST API, REST API endpoints for rate limits — official
- GitHub Changelog: Updated rate limits for unauthenticated requests (2025-05-08) — official
- PyPI Docs: API introduction/etiquette; npm blog: Acceptable Use of the Public Registry, API rate limiting — official
- Six Million (Suspected) Fake Stars on GitHub (ICSE 2026, CMU/StruDeL); 4.5 Million (Suspected) Fake Stars in GitHub (arXiv 2412.13459) — peer-reviewed research
- PyPI (APScheduler 3.11.3, hishel 1.2.1) package registry pages — verified current versions
- ThoughtWorks Technology Radar FAQ / Build Your Own Technology Radar — official first-party documentation

### Secondary (MEDIUM confidence)
- Reverse-engineering write-ups of HN and Reddit ranking algorithms (sangaline.com, righto.com, Amir Salihefendic) — cross-checked across three independent sources
- Evan Miller, "Deriving the Reddit Formula" / Wilson score interval explainers — canonical, widely-cited technique
- OSS Insight repository-ranking documentation — documented public methodology, not independently verified against source
- Data pipeline architecture literature (Alation, Dagster, DZone), idempotent-pipeline literature (Prefect, dataskew.io) — cross-corroborated general patterns
- Windows Task Scheduler wake-from-sleep community reports (Microsoft Q&A) — consistent across many independent threads, not an official Microsoft defect admission
- Reddit API pricing/rate-limit figures — aggregated from third-party developer blogs, not a canonical Reddit rate card

### Tertiary (LOW confidence)
- GitHub Trending algorithm speculation (GitHub Discussions #3083/#163970) — no official spec exists, treat any "exact formula" as unverified
- Techmeme clustering methodology (Wikipedia, 2009 HN thread) — no official spec, pieced together from secondary sources

---
*Research completed: 2026-07-19*
*Ready for roadmap: yes*
