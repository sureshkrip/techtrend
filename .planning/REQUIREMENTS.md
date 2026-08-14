# TechTrend — Requirements

**Milestone:** v1
**Core value:** Open it once a day and know, in five minutes, what is actually gaining traction in AI coding.

---

## v1 Requirements

### Data Model

- [x] **DATA-01**: System stores a canonical entity record per tracked item (repo, package, story, release) with a stable identity across runs
- [x] **DATA-02**: System stores metric observations as append-only timestamped snapshots, so velocity is computable as a delta over a time window
- [x] **DATA-03**: System stores derived scores separately from snapshots, keyed to a score version, so re-scoring never requires re-ingesting
- [x] **DATA-04**: System stores LLM enrichments cached by entity and content hash, so re-ingesting never triggers re-summarizing the same content
- [x] **DATA-05**: A partially failed daily run can be re-run safely without creating duplicate snapshots or duplicate entities

### Collection

- [x] **COLL-01**: System collects repository star counts and release events from GitHub
- [x] **COLL-02**: System backfills GitHub historical star data on first run, so velocity ranking works on day one without waiting for snapshots to accumulate
- [ ] **COLL-03**: System collects stories and points from the Hacker News Algolia API
- [ ] **COLL-04**: System collects package download counts from npm and PyPI
- [ ] **COLL-05**: System collects vendor release notes from configured RSS/Atom changelog feeds
- [x] **COLL-06**: Adding a new source requires implementing a collector interface and registering it — no changes to scoring, enrichment, or dashboard code
- [x] **COLL-07**: System authenticates to GitHub and respects documented rate limits, backing off rather than exhausting quota
- [x] **COLL-08**: System uses conditional requests (ETag / If-Modified-Since) so unchanged resources do not consume rate-limit quota
- [x] **COLL-09**: System resolves each collected item to an existing entity or creates a new one, so the same release arriving from two sources does not become two entities

### Scoring

- [x] **SCORE-01**: System ranks items by velocity over a multi-day window rather than by absolute counts
- [x] **SCORE-02**: System applies a confidence-bounded score (Wilson-style lower bound) so low-sample items cannot rank highly on percentage alone
- [x] **SCORE-03**: System applies an absolute minimum threshold per source, so trivially small items are excluded regardless of growth rate
- [x] **SCORE-04**: System normalizes scores across sources with differing scales so GitHub stars, HN points, and download counts are comparable in one ranking
- [x] **SCORE-05**: Ranking is stable enough day-to-day that the dashboard does not reshuffle completely between runs

### LLM Enrichment

- [ ] **ENR-01**: Only items clearing a configurable ranking threshold are sent to the LLM for enrichment
- [x] **ENR-02**: System enforces a hard per-run cap on enriched items, independent of the ranking threshold
- [x] **ENR-03**: LLM generates a two-line "what this is / why it matters" summary for each enriched item
- [x] **ENR-04**: LLM assigns each enriched item to exactly one of the seven defined sections
- [x] **ENR-05**: Summaries are grounded on freshly fetched source text (README, changelog, thread) — never generated from the model's parametric knowledge
- [ ] **ENR-06**: Enrichment failures do not lose ingested data; the item remains ranked and displayed without a summary

### Dashboard

- [x] **DASH-01**: User can view ranked items in a local web dashboard
- [ ] **DASH-02**: User can browse items filtered by section
- [x] **DASH-03**: User can sort items by velocity score
- [x] **DASH-04**: User can click through from any item to its original source
- [x] **DASH-05**: User can reach the official docs / getting-started page for each tracked tool
- [x] **DASH-06**: Dashboard displays when data was last successfully refreshed

### Scheduling

- [ ] **SCHED-01**: The full pipeline runs automatically once per day without user action
- [ ] **SCHED-02**: Scheduled run is configured to survive sleep/missed-window conditions on Windows

### Health

- [x] **HEALTH-01**: System records per-source success/failure and item counts for every run
- [x] **HEALTH-02**: User can see when a source has stopped returning data, rather than discovering a dead collector weeks later

---

## v2 Requirements (Deferred)

- Reddit as a source (r/LocalLLaMA, r/ChatGPTCoding) — deferred on API terms risk, not on signal value
- Seen/unseen state — track what has already been reviewed
- Reading queue — persistent flag-to-read backlog surviving runs
- Muting and filtering rules
- arXiv, Product Hunt, awesome-lists as sources
- Cross-source entity resolution (recognizing a GitHub repo and its npm package as one tool)
- User-editable section taxonomy

---

## Out of Scope

- **Publishing / newsletter / public site** — personal tool; adds presentation and cadence commitments with no value to a single user
- **Multi-user, auth, accounts** — single local user by design
- **Medium as a primary source** — no real API, hidden engagement metrics, heavily SEO-farmed in this domain
- **X/Twitter as a source** — API cost disproportionate to signal gained
- **GitHub Trending page scraping** — no official API; DOM-scraped and rots silently. Star velocity from the API gives the same signal reliably
- **Tracking technology outside AI/LLM/agentic coding** — narrowness is the design constraint that makes the tool useful
- **Summarizing every collected item** — rejected on cost; the ranking gate exists precisely to prevent this
- **A "Misc/Other" catch-all section** — identified in research as the standard back door to taxonomy drift
- **Mobile, notifications, real-time streaming, social features** — single-user local tool

---

## Traceability

| Requirement | Phase |
|-------------|-------|
| DATA-01 | Phase 1 |
| DATA-02 | Phase 1 |
| DATA-03 | Phase 1 |
| DATA-04 | Phase 2 |
| DATA-05 | Phase 1 |
| COLL-01 | Phase 1 |
| COLL-02 | Phase 1 |
| COLL-03 | Phase 3 |
| COLL-04 | Phase 3 |
| COLL-05 | Phase 3 |
| COLL-06 | Phase 1 |
| COLL-07 | Phase 1 |
| COLL-08 | Phase 1 |
| COLL-09 | Phase 1 |
| SCORE-01 | Phase 1 |
| SCORE-02 | Phase 1 |
| SCORE-03 | Phase 1 |
| SCORE-04 | Phase 1 |
| SCORE-05 | Phase 1 |
| ENR-01 | Phase 2 |
| ENR-02 | Phase 2 |
| ENR-03 | Phase 2 |
| ENR-04 | Phase 2 |
| ENR-05 | Phase 2 |
| ENR-06 | Phase 2 |
| DASH-01 | Phase 1 |
| DASH-02 | Phase 2 |
| DASH-03 | Phase 1 |
| DASH-04 | Phase 1 |
| DASH-05 | Phase 1 |
| DASH-06 | Phase 1 |
| SCHED-01 | Phase 4 |
| SCHED-02 | Phase 4 |
| HEALTH-01 | Phase 1 |
| HEALTH-02 | Phase 1 |

**Coverage:** 35/35 v1 requirements mapped. No orphans.
