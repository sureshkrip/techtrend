# Phase 1: Foundation & First Signal — GitHub, Scored and Visible - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-19
**Phase:** 1-Foundation & First Signal — GitHub, Scored and Visible
**Areas discussed:** Tracked repo universe, Day-one star history, Ranking formula knobs, Dashboard & health display

---

## Tracked Repo Universe

### How should GitHub repos enter the tracked set?

| Option | Description | Selected |
|--------|-------------|----------|
| Seed list + search discovery | Hand-written seed list of known repos PLUS daily GitHub search that promotes new repos into the set | ✓ |
| Hand-curated seed list only | Config file of repo full-names; simplest, zero discovery risk, cheap on rate limit — but tracks velocity without discovering | |
| Search-driven only | Tracked set is whatever a saved search returns; max discovery, but stricter Search API budget and known repos can fall out | |

**User's choice:** Seed list + search discovery
**Notes:** Discovery matters — the dashboard must surface things the owner hasn't already found, not just track a known list.

### Once discovered, does a repo stay tracked?

| Option | Description | Selected |
|--------|-------------|----------|
| Sticky, with quiet retirement | Snapshotted daily regardless of search presence; marked dormant after prolonged flatness, history retained | ✓ |
| Sticky forever | Simplest and safest for velocity continuity, but the set only grows and rate-limit cost creeps | |
| Only while it matches search | Smallest set, but repos blink in and out leaving gaps that break the velocity delta | |

**User's choice:** Sticky, with quiet retirement
**Notes:** Framed around velocity continuity — snapshot gaps are what break the delta math.

### How is a search hit judged AI-coding-relevant, with no LLM available?

| Option | Description | Selected |
|--------|-------------|----------|
| Topics allowlist + keyword fallback | Admit on curated topic match OR name/description keyword match; both lists in config | ✓ |
| Topics allowlist only | Highest precision, but brand-new repos often have no topics on day one — misses the freshest signal | |
| Admit all, filter at ranking | Cheapest, but pollutes the entity table permanently and the floor filters by size, not topic | |

**User's choice:** Topics allowlist + keyword fallback
**Notes:** The keyword fallback exists specifically to catch untagged brand-new repos.

### Escape hatch for deterministic filter mistakes?

| Option | Description | Selected |
|--------|-------------|----------|
| Config allowlist + blocklist | Force-include and force-exclude lists alongside the seed; dashboard stays read-only | ✓ |
| Blocklist only | Seed list already serves as force-include; simpler but asymmetric | |
| No escape hatch in Phase 1 | Fewer moving parts, but one stubborn repo forces global filter changes with side effects | |

**User's choice:** Config allowlist + blocklist
**Notes:** Curation lives in config, never the UI — preserves the dashboard-as-pure-reader rule.

---

## Day-One Star History

### How should day-one history be obtained?

| Option | Description | Selected |
|--------|-------------|----------|
| Sampled stargazer pagination | `star+json` Accept header for `starred_at`; sample pages rather than fetch all. Own API, no third party | ✓ |
| Third-party history API | star-history.com / OSS Insight; cheapest and fastest, but unofficial, no SLA, rots silently, second source of truth | |
| No backfill — absolute until history accrues | Simplest, zero cost, but fails success criterion #1 on first open | |

**User's choice:** Sampled stargazer pagination
**Notes:** Avoids the PITFALLS.md #1 silent-rot risk of an unofficial dependency.

### How much history, how tightly capped?

| Option | Description | Selected |
|--------|-------------|----------|
| ~90 days, hard per-repo request cap | Enough for a 7/14-day window plus trailing baseline; cap ~20 page requests, accept coarser curve over blowing budget | ✓ |
| ~30 days, hard per-repo cap | Cheapest and fastest, but no baseline for judging whether growth is unusual — weakens spike-vs-trend | |
| Full history, capped by total run budget | Richest data, never backfill again, but needs resumable multi-run state — too much machinery for this phase | |

**User's choice:** ~90 days, hard per-repo request cap

### Where do backfilled points live?

| Option | Description | Selected |
|--------|-------------|----------|
| Same snapshots table + provenance column | `source_kind` marks 'backfill' vs 'observed'; uniform series for the scorer, auditable, surgically purgeable, idempotent via existing UNIQUE constraint | ✓ |
| Same snapshots table, no distinction | Simplest schema, but permanently loses estimate-vs-fact and can't undo a bad backfill | |
| Separate backfill table | Cleanest separation, but complicates every scorer query and duplicates schema for the same benefit | |

**User's choice:** Same snapshots table + provenance column

### When does backfill trigger, and how are failures handled?

| Option | Description | Selected |
|--------|-------------|----------|
| On first sight, retried until complete | Per-repo completion recorded; failed/truncated repos retried next run; live snapshotting never blocked | ✓ |
| On first sight, one attempt only | No retry bookkeeping, but a transient rate-limit hit permanently leaves a repo baseline-less and invisible | |
| Explicit backfill command, run manually | Clean separation, but a manual step for every auto-discovered repo — conflicts with automatic discovery | |

**User's choice:** On first sight, retried until complete

---

## Ranking Formula Knobs

### What velocity window?

| Option | Description | Selected |
|--------|-------------|----------|
| 7-day trailing window | Spans a full week so weekday seasonality cancels without explicit normalization; responsive but damped | ✓ |
| 14-day trailing window | Smoother, better against fake-star bursts, but a hot new tool takes over a week to climb | |
| Dual window: 7d score, 14d tiebreak | Encodes spike-vs-trend directly, but two computations and a harder-to-explain first implementation | |

**User's choice:** 7-day trailing window
**Notes:** Dual-window preserved as a deferred idea if the stability metric shows it's needed.

### Where should the SCORE-03 absolute floor sit?

| Option | Description | Selected |
|--------|-------------|----------|
| Floor on absolute stars gained in window | Gates on recent movement, so genuinely-launched new repos qualify immediately while 3→12-star repos don't | ✓ |
| Floor on total star count | Simple and predictable, but systematically excludes the day-old repos the dashboard exists to catch | |
| Both floors, either must pass | Widest net, but two interacting knobs and OR-semantics that are hard to reason about | |

**User's choice:** Floor on absolute stars gained in window

### Is window + Wilson bound enough for SCORE-05 stability?

| Option | Description | Selected |
|--------|-------------|----------|
| Window + Wilson bound only, measure first | Ship the simple thing plus a rank-overlap stability metric; discover empirically whether damping is needed | ✓ |
| Add EWMA smoothing | Guarantees a calm list, but deliberately lags and risks a dashboard stable because it barely responds | |
| Add rank hysteresis | Targets churn directly, but introduces order-dependent state that breaks score purity / free re-scoring | |

**User's choice:** Window + Wilson bound only, measure before adding more
**Notes:** Hysteresis rejected specifically on the score-purity tradeoff (DATA-03).

### How much of SCORE-04 cross-source normalization to build now?

| Option | Description | Selected |
|--------|-------------|----------|
| Build the seam, calibrate later | Per-source metric→momentum step separated from source-agnostic ranking; GitHub implements it, Phase 3 plugs in | ✓ |
| Full cross-source normalization now | Phase 3 plugs in with zero scorer changes, but calibrating against never-observed scales would need redoing anyway | |
| Skip entirely, defer to Phase 3 | Simplest now, but risks a GitHub-shaped scorer that Phase 3 must tear open — violates the roadmap criterion | |

**User's choice:** Build the seam, calibrate later

---

## Dashboard & Health Display

### What should the Phase 1 dashboard look like?

| Option | Description | Selected |
|--------|-------------|----------|
| Dense sortable table | Rank, name, score, stars gained, total stars, source link, docs link; htmx sort; max scan density | ✓ |
| Card list | Reads better and leaves room for Phase 2 summaries, but poor scannability and builds for content that doesn't exist yet | |
| Table with sparklines | Backfill makes it feasible and it shows spike-vs-trend at a glance, but real extra build in a pipeline-proving phase | |

**User's choice:** Dense sortable table
**Notes:** Sparklines preserved as a deferred idea.

### How is the DASH-05 docs link resolved with no LLM?

| Option | Description | Selected |
|--------|-------------|----------|
| Homepage → README scan → repo fallback | Deterministic chain; final fallback labeled honestly as "repo" not "docs" — degrades visibly, not silently | ✓ |
| Homepage field + config override only | Zero wrong guesses, but most repos show no link on day one and DASH-05 becomes manual data entry | |
| Repo URL always | Trivially works, but collapses DASH-05 into DASH-04 — two columns going to the same place | |

**User's choice:** Homepage → README scan → repo fallback

### How loudly should stale/failed collection be surfaced?

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent header strip, escalating | Always-visible "last successful run"; escalates to a loud banner on staleness (>36h), failure, or zero-item floor breach | ✓ |
| Banner only when something's wrong | Cleanest healthy-state UI, but DASH-06 requires showing refresh time in the good case, and "no banner" ≡ "check didn't run" | |
| Header strip + separate health page | Best diagnostics, but a second view for one source; `run_manifest` data is in the DB regardless | |

**User's choice:** Persistent header strip, escalating
**Notes:** Phase 4's missed-run indicator comes for free from this. Health page preserved as deferred.

### Startup and empty state?

| Option | Description | Selected |
|--------|-------------|----------|
| Manual uvicorn start; honest empty state | Phase 4 adds the at-logon trigger; empty state names the command to run rather than rendering a blank table | ✓ |
| Manual start; blank table | Marginally less to build, but empty and broken look identical — PITFALLS #1 applied to the app itself | |
| Dashboard triggers a run if data is missing | Nicest first-run UX, but breaks the pure-downstream-reader rule and blocks page load on a full backfill | |

**User's choice:** Manual uvicorn start; honest empty state

---

## Claude's Discretion

The user took the recommended option on every question, so these are decided rather than open. Genuinely left to downstream agents:

- Exact numeric values for all config knobs (dormancy threshold, per-repo request cap, window-gain floor, staleness threshold) — shape decided, values are Claude's call, but all must be config rather than code constants
- The specific stargazer sampling algorithm (binary search vs. fixed stride vs. adaptive)
- Config file format and location (separate from `.env` secrets)
- `score_version` bookkeeping and how a formula change triggers a re-score
- How release events (COLL-01) are represented alongside stars
- Testing approach — two concrete assertions from PITFALLS.md worth encoding

## Deferred Ideas

- Sparklines in the dashboard table — feasible for free given the 90-day backfill; later polish pass
- Dedicated `/health` page over `run_manifest` — data is being written regardless
- Dual 7d/14d window with spike detection — revisit if the stability metric shows the single window is insufficient
- EWMA smoothing / rank hysteresis — explicitly rejected; hysteresis should stay rejected unless score purity is reconsidered
