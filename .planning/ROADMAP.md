# Roadmap: TechTrend

## Overview

TechTrend starts from the thinnest slice that is actually useful: one collector (GitHub, backfilled so velocity works from day one), a confidence-bounded scorer, and a minimal dashboard — no LLM, nothing to pay for, something real to look at immediately. Phase 2 turns that ranked list into the product's actual differentiator by adding cost-gated LLM summarization and section classification, with the spend controls (threshold + hard cap) landing in the same phase as the first model call, never after. Phase 3 proves the collector plugin boundary by adding Hacker News, npm/PyPI, and vendor changelogs without touching the scorer, gate, enricher, or dashboard. Phase 4 closes the loop by wiring the daily scheduler — deliberately last, since idempotency is already a property of the schema and pipeline stages by then, not something the scheduler has to provide.

This sequencing intentionally departs from a purely horizontal build order (schema, then collector, then scorer, then dashboard as four separate milestones). Those four pieces are combined into Phase 1 because none of them is independently useful to a user — the goal-backward test ("what must be true for the user") isn't satisfied until a ranked, real, clickable list renders in a browser. Idempotency (append-only snapshots, dedup keys), collector health logging, and content-hash-keyed enrichment caching are each built alongside the work they protect rather than retrofitted in a cleanup pass.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation & First Signal — GitHub, Scored and Visible** - Schema, backfilled GitHub collector, confidence-bounded velocity scorer, and a minimal dashboard — real ranked data, visible, before any LLM spend
- [ ] **Phase 2: Cost-Gated LLM Enrichment** - Gate + hard cap + LLM summarize/classify into the seven sections, cached by content hash, never losing ranked data on failure
- [ ] **Phase 3: Source Breadth — Discourse, Downloads & Changelogs** - Hacker News, npm/PyPI, and vendor changelogs added through the existing collector plugin interface
- [ ] **Phase 4: Autonomous Daily Scheduling** - Windows Task Scheduler wired with wake/missed-run settings so the pipeline runs unattended every day

## Phase Details

### Phase 1: Foundation & First Signal — GitHub, Scored and Visible

**Goal**: A user can open the local dashboard and see real AI-coding GitHub repositories ranked by genuine velocity (not raw star count), backed by durable historical data and visible source health — reachable before any LLM cost is incurred.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-05, COLL-01, COLL-02, COLL-06, COLL-07, COLL-08, COLL-09, SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05, DASH-01, DASH-03, DASH-04, DASH-05, DASH-06, HEALTH-01, HEALTH-02
**Success Criteria** (what must be TRUE):

  1. Opening the dashboard shows a ranked list of real GitHub AI-coding repos ordered by velocity, where a small repo gaining stars quickly outranks a large repo that has gone flat.
  2. Rankings are stable day-to-day — a repo with only 2-10 stars cannot rocket to the top on percentage growth alone, and the list doesn't completely reshuffle between runs.
  3. Every item links through to its GitHub source and to its documentation/getting-started page.
  4. The dashboard shows when data was last successfully refreshed, and if GitHub collection fails or returns no items, that failure is visibly flagged instead of the section silently going stale.
  5. Re-running a partially-failed daily collection does not create duplicate entities or duplicate historical snapshots.

**Plans**: 5/6 plans executed

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Project scaffold, four-table SQLite schema, config surface, Wave 0 test harness

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Walking Skeleton: fixture-backed ingest writes real rows, FastAPI dashboard renders them

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Collector plugin seam, live GitHub collection, identity/snapshot pipeline, run health, docs links

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — Wilson-bounded velocity scoring with absolute floor, normalization seam, stability metric
- [x] 01-05-PLAN.md — Sampled stargazer backfill with hard request cap and honest degraded state (D-08a)

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 01-06-PLAN.md — Dense sortable dashboard, honest link labels, escalating health strip

**UI hint**: yes

### Phase 2: Cost-Gated LLM Enrichment

**Goal**: High-velocity items surviving the ranking gate receive a grounded two-line summary and a section assignment, within a hard-capped LLM budget, and enrichment problems never cost the user visibility into already-ranked data.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: DATA-04, ENR-01, ENR-02, ENR-03, ENR-04, ENR-05, ENR-06, DASH-02
**Success Criteria** (what must be TRUE):

  1. Only items clearing the configured ranking threshold — and never more than the hard per-run cap, even on an unusually busy day — are sent to the LLM for enrichment.
  2. Each enriched item shows a two-line "what this is / why it matters" summary and is filed into exactly one of the seven fixed sections; the user can browse/filter the dashboard by section.
  3. A summary for a brand-new or obscure tool reflects its actual fetched README/changelog/thread text, not a plausible-sounding fabrication from the model's own training knowledge.
  4. Re-running the pipeline on unchanged items never re-calls the LLM (same content hash hits the cache), and if enrichment fails for an item, that item still displays ranked in the dashboard without a summary rather than disappearing.

**Plans**: TBD
**UI hint**: yes

### Phase 3: Source Breadth — Discourse, Downloads & Changelogs

**Goal**: The dashboard reflects the project's full multi-source premise — Hacker News discourse, npm/PyPI download traction, and vendor changelog releases all appear alongside GitHub, flowing through the same identity-resolution, scoring, and enrichment pipeline with no changes to that pipeline's code.
**Mode:** mvp
**Depends on**: Phase 1, Phase 2
**Requirements**: COLL-03, COLL-04, COLL-05
**Success Criteria** (what must be TRUE):

  1. Hacker News stories, npm/PyPI download velocity, and vendor changelog releases each appear in the dashboard's ranked, sectioned list alongside GitHub items.
  2. The same release mentioned on both GitHub and a vendor changelog resolves to one entity, not two duplicate dashboard rows.
  3. Adding these three sources required only new collector modules plus a registry entry — no changes to the scorer, gate, enricher, or dashboard code.

**Plans**: TBD

### Phase 4: Autonomous Daily Scheduling

**Goal**: The full pipeline runs on its own every day, including across sleep/wake cycles on Windows, so the dashboard is always current when the user opens it without them remembering to trigger anything.
**Mode:** mvp
**Depends on**: Phase 1, Phase 2, Phase 3
**Requirements**: SCHED-01, SCHED-02
**Success Criteria** (what must be TRUE):

  1. The full collect → score → enrich pipeline runs automatically once per day with no manual action from the user.
  2. If the machine was asleep or off at the scheduled time, the run still executes (wake timers, wake-to-run, and run-if-missed are all explicitly configured) rather than silently skipping that day.
  3. The dashboard's "last successful run" indicator reflects a same-day refresh under normal conditions, so a missed run is immediately visible without digging into Task Scheduler.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|-----------------|--------|-----------|
| 1. Foundation & First Signal | 5/6 | In Progress|  |
| 2. Cost-Gated LLM Enrichment | 0/TBD | Not started | - |
| 3. Source Breadth | 0/TBD | Not started | - |
| 4. Autonomous Daily Scheduling | 0/TBD | Not started | - |
