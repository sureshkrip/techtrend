# Architecture Research

**Domain:** Personal content-aggregation / ETL-plus-dashboard system (daily multi-source collection, velocity ranking, LLM enrichment, local single-user web dashboard)
**Researched:** 2026-07-19
**Confidence:** MEDIUM (general ETL/data-pipeline architecture patterns are well-established and cross-corroborated across independent sources; no single authoritative "trend dashboard" reference architecture exists, so patterns are adapted from broader data-engineering and plugin-architecture literature, then scaled down to single-user/local scope)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  COLLECT (plugin layer — one adapter per source, runs independently)  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ GitHub   │ │ HN       │ │ RSS/     │ │ npm/PyPI │ │ Vendor     │  │
│  │ Collector│ │ Algolia  │ │ Changelog│ │ Registry │ │ Changelog  │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘  │
│       └────────────┴─────────────┴────────────┴─────────────┘        │
│                              │  (raw records, source-shaped)          │
├──────────────────────────────┼────────────────────────────────────────┤
│                    NORMALIZE + IDENTITY RESOLVE                        │
│         raw record → canonical CollectedItem → match/create Entity     │
├──────────────────────────────┼────────────────────────────────────────┤
│                              ▼                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  STORAGE (single embedded relational DB — the shared contract)  │  │
│  │  entities  │  snapshots (append-only)  │  scores  │ enrichments │  │
│  │            │  run_manifest (idempotency bookkeeping)            │  │
│  └────────────────────────────────────────────────────────────────┘  │
│              │                    │                    │              │
│         (reads snapshots)   (reads score+entity   (reads entity+      │
│              │              gate threshold)        recent snapshot)   │
│              ▼                    ▼                    ▼              │
│  ┌──────────────┐    ┌──────────────────┐   ┌───────────────────┐    │
│  │  SCORE        │    │  GATE             │   │  ENRICH (LLM)      │    │
│  │  (derive       │    │  (deterministic  │   │  (summarize +      │    │
│  │  velocity from │    │  threshold)      │   │  classify, cached  │    │
│  │  snapshot deltas)│  │                  │   │  by content_hash)  │    │
│  └──────────────┘    └──────────────────┘   └───────────────────┘    │
│                              │                                        │
├──────────────────────────────┼────────────────────────────────────────┤
│                        SERVE (dashboard)                               │
│         read-only queries over entities+scores+enrichments             │
│         browse by section, sort by velocity, click through to source   │
└──────────────────────────────────────────────────────────────────────┘
```

**Corrected pipeline stages:** the natural decomposition is `collect → normalize → identity-resolve → snapshot → score → gate → enrich (LLM) → serve` — very close to the proposed `collect → normalize → dedupe → snapshot → score → enrich → serve`, with one substantive correction: **"dedupe" should be reframed as "identity resolution."** Removing exact duplicate records is trivial; the real work is deciding *"is this raw record a new entity, or a new observation of an entity I already track?"* — that decision must happen before the snapshot write (snapshots need a stable `entity_id` foreign key) and is architecturally distinct from simple deduplication. There is also an explicit **gate** seam between score and enrich (the deterministic ranking threshold that controls LLM spend) that the proposed decomposition folds into "enrich" — it deserves to be named as its own seam because it is a pure, cheap, synchronous decision made entirely from data already in `scores`, with no I/O.

### Where the real seams are

| Seam | Why it's a real boundary |
|---|---|
| collect ↔ normalize | This is the **collector plugin interface** (Q2). Everything on the left of this seam is source-specific and heterogeneous; everything on the right is source-agnostic. |
| normalize ↔ snapshot (via identity-resolve) | This is the **hardest correctness problem** in the system: matching a raw record to a stable entity. Get this wrong and velocity math silently corrupts (same tool tracked as two entities → its history is split; two different tools merged → nonsense velocity). |
| snapshot ↔ score | This is the **re-scoring-without-re-ingesting seam** (Q3/Q6). Score is a pure function of `(entities, snapshots)` and must be re-runnable on demand with zero network I/O. |
| score ↔ enrich | This is the **cost-control seam** (Q5) — a config threshold, not a code path, and it is the only place LLM spend is decided. |
| enrich ↔ serve | This is the **re-ingesting-without-re-summarizing seam** (Q3/Q5) — the dashboard never triggers or waits on an LLM call; it only reads what's cached. |

## Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Collector (×N, one per source) | Fetch raw data from one external source; know that source's auth/rate-limit/pagination quirks; emit raw records in a source-native shape | Small module/class implementing a shared `Collector` interface; one file per source under `collectors/` |
| Normalizer | Map each source's raw shape into one canonical `CollectedItem` shape (name, url, type, metric readings, docs link candidate) | Pure function, usually colocated with or called by each collector (each collector owns its own normalize step, since only it knows the raw shape) |
| Identity Resolver | Decide whether a normalized item matches an existing `entity` (by `(source, source_native_id)` key) or is new; create/update the entity row | Single shared function called by the orchestrator after every collector run, not by each collector |
| Snapshot Writer | Persist one immutable time-series row per (entity, run date, metric) | Upsert (`INSERT ... ON CONFLICT DO NOTHING/UPDATE`) keyed on a unique `(entity_id, collected_at, metric_name)` constraint |
| Scorer | Compute velocity/momentum from snapshot history; write/replace rows in `scores` | Standalone script/function, runs over `(entities, snapshots)` only — no network calls, fully replayable |
| Gate | Decide which entities clear the LLM-enrichment threshold for the current run | Pure query against `scores` + a config value; no side effects of its own |
| Enricher | Call the LLM to summarize + classify gated items; cache result keyed by content hash so identical content is never resent | Standalone script/function; checks `enrichments` cache before every call |
| Orchestrator | Drive the daily run: invoke each collector (isolated failure), then identity-resolve, then score, then gate+enrich; record stage completion in `run_manifest` | Single entry-point script invoked by the OS scheduler (cron / Task Scheduler); the *only* component that knows the full stage order |
| Dashboard (serve) | Read-only web UI: list by section, sort by velocity, link to source and docs | Reads directly from the same DB; never calls collectors, scorer, or LLM |

## Recommended Project Structure

```
src/
├── collectors/                 # one module per source — the plugin seam
│   ├── collector.interface.ts  # shared Collector contract (fetch + normalize)
│   ├── github.collector.ts     # GitHub stars/activity
│   ├── hn.collector.ts         # HN Algolia API
│   ├── rss.collector.ts        # generic RSS/changelog adapter (config-driven, reused per feed)
│   ├── npm.collector.ts        # npm registry download velocity
│   ├── pypi.collector.ts       # PyPI registry download velocity
│   └── registry.ts             # explicit list of enabled collectors (add-a-source = add one line here)
├── pipeline/
│   ├── identity-resolve.ts     # normalized item → entity (match-or-create)
│   ├── snapshot.ts             # write append-only metric rows
│   ├── score.ts                # derive velocity from snapshot history (no I/O)
│   ├── gate.ts                 # threshold check against scores
│   ├── enrich.ts                # LLM summarize + classify, cache-checked
│   └── orchestrator.ts          # daily run driver + run_manifest bookkeeping
├── db/
│   ├── schema.sql               # entities, snapshots, scores, enrichments, run_manifest
│   └── migrations/
├── server/                      # dashboard backend (reads DB, serves API/pages)
└── web/                         # dashboard frontend (browse/sort/click-through)
```

### Structure Rationale

- **`collectors/`:** isolates everything source-specific behind one interface. Adding a source means adding one new file + one registry line — nothing else in the tree changes. This is deliberately the most "pluggable" folder in the project because it is also the one most likely to be extended over time and worked on in parallel.
- **`pipeline/`:** each file is a separate, independently invokable stage matching a seam in the diagram above. Because these are separate files/functions (not one monolithic "process everything" function), the scorer and enricher can be run standalone (`node pipeline/score.ts`) for debugging or backfills without re-running collection.
- **`db/schema.sql`:** the schema is the actual contract between every component; it belongs in its own reviewable file rather than being implied by ORM models scattered across collectors.

## Architectural Patterns

### Pattern 1: Collector Plugin Interface

**What:** A single shared interface every source-specific collector implements, plus a registry the orchestrator iterates — orchestration code never has a per-source branch.

**When to use:** Whenever the number of sources is expected to grow (this project starts with ~5-8 candidate sources and explicitly expects more over time).

**Trade-offs:** Slightly more boilerplate per source (an interface implementation instead of a one-off script) in exchange for the orchestrator, scorer, gate, enricher, and dashboard never needing to know a new source was added.

**Example (illustrative pseudocode — actual language/runtime deferred to STACK.md):**
```typescript
interface Collector {
  sourceId: string;                      // "github", "hn", "npm", ...
  fetch(sinceRunDate: string): Promise<RawRecord[]>;
  normalize(raw: RawRecord): CollectedItem; // → canonical shape, source owns this mapping
}

// registry.ts — the ONLY file touched to add a source
export const collectors: Collector[] = [githubCollector, hnCollector, npmCollector];

// orchestrator.ts — never branches on source
for (const collector of collectors) {
  try {
    const raw = await collector.fetch(runDate);
    const items = raw.map(collector.normalize);
    for (const item of items) await identityResolveAndSnapshot(item, runDate);
    recordRunManifest(runDate, `collect:${collector.sourceId}`, "success");
  } catch (err) {
    recordRunManifest(runDate, `collect:${collector.sourceId}`, "failed", err);
    // one source failing does not abort the run
  }
}
```

### Pattern 2: Append-Only Snapshot + Derived Score Separation

**What:** Raw metric observations are written once and never mutated (`snapshots`); velocity/rank is a separately computed, freely replaceable table (`scores`) derived purely from `snapshots` + `entities`.

**When to use:** Any time "trend"/"velocity"/"momentum" is a first-class requirement — you cannot compute a trend from a single current value; you need history, and the scoring formula will change before the ingestion format does.

**Trade-offs:** One extra table and one extra pass versus computing velocity inline during collection — but this is what makes re-scoring free (Q3) and lets the scoring algorithm evolve independently of everything upstream of it.

**Example:**
```sql
-- snapshots: append-only, immutable
INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value)
VALUES (?, ?, 'stars', ?)
ON CONFLICT (entity_id, collected_at, metric_name) DO NOTHING;

-- score.ts: pure function of existing data, no network I/O, fully re-runnable
SELECT entity_id, metric_name,
       metric_value - LAG(metric_value) OVER (
         PARTITION BY entity_id, metric_name ORDER BY collected_at
       ) AS delta
FROM snapshots
WHERE collected_at >= date('now', '-7 days');
```

### Pattern 3: Cache-Gated Enrichment (content-hash keyed)

**What:** Before calling the LLM, hash the fields that would be sent to it (name, description, recent metric summary). Look up `(entity_id, content_hash)` in `enrichments`; only call the LLM on a miss.

**When to use:** Whenever LLM calls are metered/costed and the same entity is likely to be re-processed across runs (true here: an item that already cleared the threshold yesterday will very likely clear it again today).

**Trade-offs:** Requires computing and storing a hash, and requires a decision about what "meaningfully changed" means for a re-summarize trigger — but guarantees an item is genuinely never summarized twice for the same content, and survives ingestion re-runs (Q4) and prompt iteration (only items with no cached hash for the *new* prompt version get re-run).

## Data Flow

### Daily Run Flow

```
Scheduler trigger (cron / Task Scheduler)
    ↓
Orchestrator reads run_manifest for today's run_date
    ↓ (skip stages already marked "success" for this run_date — idempotent re-entry)
For each registered collector (isolated try/catch):
    fetch → normalize → identity-resolve (match-or-create entity) → write snapshot row
    ↓
Scorer: recompute velocity for all entities with new/changed snapshots
    ↓
Gate: select entities whose score clears the configured threshold
    ↓
Enricher: for gated entities, check enrichments cache by content_hash
    → cache hit: reuse; cache miss: call LLM, summarize + classify into one of 7 sections, write cache row
    ↓
Dashboard: on page load, query entities ⋈ scores ⋈ enrichments (read-only, no pipeline stage invoked)
```

### Key Data Flows

1. **Collection → identity:** raw records never touch the entity/snapshot tables directly; they pass through normalize + identity-resolve first, so every write to `snapshots` is guaranteed to reference a valid, deduplicated `entity_id`.
2. **Snapshots → score → gate → enrich:** strictly one-directional and layered — score never calls a collector, gate never calls the LLM directly, enrich never writes to snapshots. Each stage only reads the output of the one before it and writes to its own table.
3. **Dashboard is a pure downstream reader:** it never triggers collection, scoring, or enrichment — it just reflects whatever the most recent completed pipeline run produced. This is what makes "something visible in the dashboard" achievable before the LLM stage even exists (Q6).

## The Data Model Seam (entity / snapshot / score / enrichment)

This is the load-bearing design decision for the whole system — it directly answers Q3 and Q5.

| Table | Nature | Written by | Read by | Purpose |
|---|---|---|---|---|
| `entities` | Slowly-changing identity | Identity resolver | Everything downstream | The canonical "what is this thing" — one row per tracked tool/package/thread, keyed by `(source, source_native_id)` |
| `snapshots` | Append-only, immutable fact log | Collector pipeline (via snapshot writer) | Scorer only | The raw historical ledger metrics are measured from; never updated, only inserted, unique on `(entity_id, collected_at, metric_name)` |
| `scores` | Derived, fully replaceable | Scorer | Gate, dashboard | Velocity/rank computed *purely* from `entities` + `snapshots`; safe to `DELETE` and recompute at any time with zero network calls |
| `enrichments` | Derived, cached, keyed by content hash | Enricher | Dashboard | LLM output (summary + section), keyed on `(entity_id, content_hash)` so unchanged content is never re-sent to the model |
| `run_manifest` | Orchestration bookkeeping | Orchestrator | Orchestrator (on resume) | One row per `(run_date, stage)`, records success/failure so a partially-failed day can resume without redoing completed stages |

**Why this separation makes re-scoring free:** `scores` has no foreign dependency on anything except data already sitting in `entities`/`snapshots`. Changing the velocity formula (e.g., switching from raw delta to a decayed-weighted formula) means deleting and recomputing `scores` only — no network call, no re-fetch, no LLM call, and `enrichments` is completely untouched.

**Why this separation makes re-ingesting free of re-summarizing:** Enrichment keys on `content_hash`, not on `collected_at` or run date. Running the collector again today writes new `snapshots` rows and possibly updates `entities.last_seen_at`, but if the fields that feed the LLM prompt (name, description, recent metric summary) haven't materially changed, the hash is identical, the enrichment cache hits, and the LLM is never called again for that item.

**Deliberate simplification (call out, don't over-build):** identity resolution in v1 should key strictly on `(source, source_native_id)` — e.g., a GitHub repo and an npm package that happen to represent "the same tool" are treated as **two separate entities**, not merged. Cross-source entity resolution (fuzzy-matching "this HN post and this GitHub repo are about the same tool") is a much harder problem with real false-positive risk, and nothing in the requirements demands it for v1. Revisit only if duplicate dashboard entries prove to be a real usability problem in practice.

## Idempotency and Re-Runs

The constraint "a daily job that partially fails must be safely re-runnable" is not solved by one component — it's enforced at every stage boundary via natural keys and a lightweight manifest, not via a retry framework:

| Where | Mechanism |
|---|---|
| Per collector | Wrapped in its own try/catch inside the orchestrator loop; one source failing (rate limit, API outage) does not abort the run or block other collectors |
| Snapshot write | `UNIQUE(entity_id, collected_at, metric_name)` + upsert — re-running the same day's collection never creates duplicate history rows |
| Score computation | Fully deterministic function of `(entities, snapshots)` for a given run_date — safe to recompute any number of times, always converges to the same result (`score_version` column records which formula produced it, for auditability across formula changes) |
| Enrichment | `UNIQUE(entity_id, content_hash)` — re-running the enrichment step after a partial failure re-checks the cache first, so already-summarized items are never billed again |
| Orchestration | `run_manifest(run_date, stage, status)` — the orchestrator checks this table before invoking each stage/collector and skips anything already marked `success` for today, so re-invoking the whole daily script mid-failure resumes rather than restarts |

The practical implication for a single-user local system: this does **not** require a message queue, distributed lock, or workflow engine. It requires (a) unique constraints in the schema, (b) upsert semantics on every write, and (c) one small bookkeeping table. That's proportionate to the actual scale (one machine, one run/day, a few dozen sources at most).

## LLM Enrichment: Argument for Decoupling It From Ingestion

**Decouple it — logically (separate stage, separate table, separate cache key), not necessarily physically (no queue/worker service needed at this scale).**

Reasons for decoupling:
1. **Cost control already forces it.** The project's own constraint — a deterministic ranking gate controls what reaches the LLM — cannot be expressed as anything *but* a separate stage; "enrich everything during collection" and "enrich only what clears a threshold computed from collection" are mutually exclusive designs.
2. **Failure isolation.** If the LLM API is down or rate-limited, ingestion and scoring must still complete and be visible in the dashboard (minus summaries) rather than the whole day's run failing. Coupling enrichment into collection means one LLM outage blocks fresh data from ever landing.
3. **Never-summarize-twice caching.** A content-hash-keyed cache is only meaningful as an independent lookup step; if enrichment is inline with collection, there is no natural place to check "have I already paid for this" before paying for it again.
4. **Latency/rate mismatch.** API/RSS collection is fast (seconds); LLM summarization is comparatively slow and rate-limited. Coupling them makes the whole run only as fast as the slowest LLM call, and a burst of newly-gated items (e.g., a big release day) can create backpressure that has nothing to do with data collection.
5. **Independent iteration.** The section taxonomy is explicitly flagged in `PROJECT.md` as something to "revisit if classification error is high in practice," and prompt wording will be tuned over time. A decoupled enrichment stage means taxonomy/prompt changes can be re-applied to already-collected historical entities (by bumping `prompt_version` and re-running only the enrichment stage) without touching collectors at all.

Caveat against over-engineering the decoupling: at single-user/local scale there is no case for Kafka, a message broker, or a separate long-running worker process. "Decoupled" here means: a separate function/script, a separate table, and a cache key — invoked as a second pass in the same daily orchestrator run, not a separate service.

## Build Order

Dependency chain, thinnest-first:

1. **Schema first.** `entities`, `snapshots`, `scores`, `enrichments`, `run_manifest` — every other component reads/writes this contract; nothing else can be built (even a "fake" collector) without it existing.
2. **One collector, end-to-end through snapshot.** Pick the simplest source to implement the plugin interface against — HN Algolia is the best first pick (no auth, clean JSON, generous free API) or GitHub's public API (no auth needed for read-only, well-documented). Prove `fetch → normalize → identity-resolve → snapshot write` for exactly one source before adding a second.
3. **Scorer, standalone.** A pure query over `snapshots`, runnable independently of collection. **Caveat:** velocity is undefined from a single snapshot — the thinnest slice needs either (a) a naive fallback score for day 1 (e.g., rank by absolute value until a second data point exists), or (b) running the collector locally twice with a manufactured time gap to prove the delta math, or (c) picking a source whose API can return historical points in one call (some GitHub star-history style endpoints can) to get a real velocity signal on day one. This should be decided explicitly in the roadmap rather than discovered mid-build.
4. **Minimal dashboard.** Read-only list view over `entities ⋈ scores`, sorted by score, linking out to source URL. **This is the thinnest end-to-end vertical slice that proves the concept** — one source, real data, something ranked and visible — and it requires zero LLM involvement. This is the right point to demo/validate before adding cost (LLM) or breadth (more sources).
5. **Gate + Enrichment stage.** Add the threshold config, the LLM call, the content-hash cache, and backfill summaries onto the entities already visible in the dashboard from step 4. Section taxonomy and docs-link display land here.
6. **Second and third collectors.** This is the real test of the plugin seam — adding sources 2 and 3 should touch only `collectors/` and the registry, not the pipeline, scorer, gate, enricher, or dashboard. If adding a source requires touching anything outside `collectors/`, the interface boundary from step 2 was drawn wrong and should be corrected here, before more sources are added.
7. **Scheduler wiring last.** Cron / Task Scheduler invocation of the orchestrator is the least architecturally interesting piece — by this point idempotency is already a property of the schema and stages (steps 1-3), not something the scheduler adds. Wiring the daily trigger is the last, lowest-risk step precisely because everything it invokes is already safe to invoke repeatedly.

**Thinnest viable vertical slice, restated:** one collector → normalize → identity-resolve → snapshot → naive score → minimal dashboard list. No LLM, no taxonomy, no second source. This proves the hardest structural bets (plugin boundary shape, snapshot/score separation, something-renders-in-a-browser) before spending any LLM budget or building breadth.

## Scaling Considerations

At this project's actual scale (one user, one machine, a few dozen sources at most, daily cadence), "scaling" mostly means "years of accumulated history," not concurrent users:

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Day 1 – few sources, few months of history | Embedded relational DB (single file) is more than sufficient; no indexing concerns yet |
| 1-2 years of daily snapshots, dozens of sources | `snapshots` becomes the largest table by far (one row per entity per metric per day) — add an index on `(entity_id, collected_at)`; consider pruning/aggregating snapshot granularity older than N months (e.g., collapse daily → weekly) since the dashboard cares about recent velocity, not exact historical values from a year ago |
| Many years / hundreds of tracked entities | Scoring pass may need to scope its window (e.g., only recompute scores for entities with snapshots in the last 30 days) rather than recomputing from full history every run |

### Scaling Priorities

1. **First bottleneck: `snapshots` table growth**, not compute — this is an append-only log with one row per (entity, metric, day). Mitigate with an index and, eventually, a retention/rollup policy for old rows — never delete without rolling up, since long-term velocity trends are part of the product's value.
2. **Second bottleneck: LLM cost creep as tracked-entity count grows** — mitigated entirely by the existing gate mechanism (threshold is config, not code) and the content-hash cache (re-summarization only happens on real content change), so this is already designed for rather than something to fix later.

## Anti-Patterns

### Anti-Pattern 1: Computing velocity inline during collection

**What people do:** Compute and store "current velocity" as a column on the entity row at collection time, alongside the raw metric.
**Why it's wrong:** Couples the scoring formula to the collection code path — changing how velocity is computed (which will happen; ranking algorithms get tuned) then requires re-running collectors just to get a new number, even though no new data exists. It also makes the entity row mutable in a way that destroys the audit trail of "what did we think this item's velocity was on date X."
**Instead:** Store only raw observations in `snapshots`; compute velocity in a separate, replayable `scores` pass keyed by `score_version`.

### Anti-Pattern 2: Summarizing every collected item "just in case"

**What people do:** Call the LLM for every normalized item as part of ingestion, then filter/rank afterward, reasoning "we might want the summary later anyway."
**Why it's wrong:** This is explicitly rejected in `PROJECT.md` on cost grounds (150-300 items/day), and it also removes the gate as an architectural seam — enrichment stops being cheap to skip and becomes a fixed cost of every run regardless of how many items actually matter.
**Instead:** Gate strictly on the deterministic score threshold before any LLM call; enrichment cost scales with "things that matter," not "things that were collected."

### Anti-Pattern 3: Cross-source entity resolution as a v1 requirement

**What people do:** Try to merge "the same tool" across GitHub, npm, and HN into a single entity via fuzzy name-matching before any real user has looked at the dashboard.
**Why it's wrong:** This is a genuinely hard, error-prone problem (false merges are worse than duplicates — they silently corrupt one entity's history with another's) and nothing in the current requirements needs it; the taxonomy explicitly allows "one obvious home" per item, not per abstract cross-source concept.
**Instead:** Key entities strictly on `(source, source_native_id)` in v1; treat visible duplicates as a UX polish problem to solve later if it actually shows up, not an architecture problem to pre-solve.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| GitHub API | Collector polls repo metadata (stars, activity) on a schedule | Unauthenticated calls are rate-limited far more tightly than authenticated ones — a personal access token is worth the setup even for a single-user tool |
| HN Algolia API | Collector queries by keyword/time window | Free, no auth, clean JSON — good first-collector candidate per Q6 |
| RSS/vendor changelogs | Generic RSS collector, config-driven list of feed URLs | One collector implementation, many configured instances — not one collector class per vendor |
| npm / PyPI registries | Collector polls download-count endpoints | Registries generally expose historical download counts natively, which is useful for bootstrapping velocity without waiting for multiple local snapshot runs |
| LLM provider | Enricher calls the model only for gated items, cache-checked first | Treat as any other rate-limited external dependency — isolate failures the same way a collector isolates a source outage |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Collector ↔ Orchestrator | Direct function call, shared `Collector` interface | No events/queues needed at this scale; a plain interface + registry list is the right amount of indirection |
| Pipeline stages (collect/score/gate/enrich) ↔ each other | Shared DB tables only — no direct function calls between stages | Each stage reads what the previous stage wrote; this is what makes each stage independently re-runnable and testable |
| Dashboard ↔ Pipeline | Dashboard reads DB directly (or via a thin read API); never invokes a pipeline stage | Keeps the dashboard purely presentational and safe to reload without side effects |

## Sources

- [Data Pipeline Architecture: 9 Patterns & Best Practices for Scalable Systems (Alation)](https://www.alation.com/blog/data-pipeline-architecture-patterns/) — MEDIUM confidence (web, cross-corroborated)
- [Data Pipeline Architecture: 5 Design Patterns with Examples (Dagster)](https://dagster.io/guides/data-pipeline-architecture-5-design-patterns-with-examples) — MEDIUM confidence
- [Plug-in Architecture and the story of the data pipeline (Medium)](https://medium.com/omarelgabrys-blog/plug-in-architecture-dec207291800) — MEDIUM confidence
- [The Right ETL Architecture for Multi-Source Data Integration (DZone)](https://dzone.com/articles/etl-architecture-multi-source-data-integration) — MEDIUM confidence
- [Schema design for time series data (Google Cloud Bigtable docs)](https://cloud.google.com/bigtable/docs/schema-design-time-series) — MEDIUM confidence (official vendor docs, cross-corroborated with AWS Timestream docs)
- [Data modeling (Amazon Timestream docs)](https://docs.aws.amazon.com/timestream/latest/developerguide/data-modeling.html) — MEDIUM confidence
- [Idempotent Data Pipelines: Safe to Re-Run Every Time](https://fawadhs.dev/blog/idempotent-data-pipeline-design-safe-rerun) — MEDIUM confidence (cross-corroborated across Prefect, dataskew.io, dev.to)
- [The Importance of Idempotent Data Pipelines for Resilience (Prefect)](https://www.prefect.io/blog/the-importance-of-idempotent-data-pipelines-for-resilience) — MEDIUM confidence
- [Data Pipeline Design Patterns: Idempotency, DLQ, CDC and 5 More (dataskew.io)](https://dataskew.io/blog/data-pipeline-design-patterns/) — MEDIUM confidence
- [Building an AI Document Processing Pipeline with Kafka: Ingest, Enrich, Embed, Store (Markaicode)](https://markaicode.com/architecture/kafka-llm-processing-pipeline/) — MEDIUM confidence
- [Prompt2DAG: A Modular Methodology for LLM-Based Data Enrichment Pipeline Generation (arXiv)](https://arxiv.org/html/2509.13487v1) — MEDIUM confidence

Note: no source addresses this exact product category ("personal trend-tracking dashboard with velocity ranking and LLM gating") directly — findings are synthesized from general ETL/data-pipeline architecture, time-series schema design, idempotent-pipeline, and LLM-enrichment-decoupling literature, then explicitly scaled down to single-user/local deployment. Treat the overall shape as HIGH-confidence (these are long-settled data-engineering patterns) and the specific scale-down judgment calls (no queue, no distributed lock, embedded DB implication) as this researcher's reasoned application of those patterns to the stated constraints, not a directly-sourced claim.

---
*Architecture research for: personal AI/LLM ecosystem trend-tracking dashboard (ETL-plus-dashboard, single user, daily batch)*
*Researched: 2026-07-19*
