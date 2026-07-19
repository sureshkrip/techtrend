# Feature Research

**Domain:** Personal, locally-run AI/LLM ecosystem trend-tracking dashboard (single user, daily ingestion, velocity ranking, LLM summarization)
**Researched:** 2026-07-19
**Confidence:** MEDIUM overall — ranking-formula math is HIGH-confidence (textbook, cross-checked, decades of production use at HN/Reddit); exact proprietary algorithms (GitHub Trending, Techmeme clustering) are LOW-confidence speculation/reverse-engineering since neither publishes their internals; dedup and cold-start technique recommendations are MEDIUM (established patterns, not verified against a specific paper for this exact domain)

---

## Part 1: How Real Aggregators Rank — Concrete Formulas

This is the crux of the product, so the math is spelled out before the feature tables.

### Hacker News: gravity-decay formula

```
Score = (P - 1) / (T + 2)^G
```
- `P` = points (upvotes), minus 1 to discount the submitter's own vote
- `T` = hours since submission
- `G` = gravity constant, default **1.8**

Because `T` is *exponentiated* while `P` is only linear, age dominates over time no matter how popular an item is — after ~20 hours even the most-upvoted story falls off the front page. This is a **decay-first** design: it guarantees churn, which is exactly what a "what's new today" dashboard needs. Cross-checked across three independent reverse-engineering writeups (sangaline.com's live-scrape analysis, righto.com's Arc source-code read, and Amir Salihefendic's widely-cited breakdown) — treat the formula itself as HIGH confidence.

### Reddit: hot ranking (log-vote + linear time)

```
order = log10(max(|ups - downs|, 1)) + sign(ups - downs) * (seconds_since_epoch / 45000)
```
- The **log term** is the key trick for star/vote-count normalization: the first 10 votes move the score as much as the next 100, and those as much as the next 1,000. This compresses large absolute counts so a viral newcomer isn't permanently buried under a legacy giant's raw magnitude.
- `45000` seconds ≈ 12.5 hours — every 12.5 hours of age costs a flat +1 to the score another post needs to catch up.
- Net effect: **upvote velocity** (rate, not total) is what actually separates rankings, because the log has already flattened the "total votes" contribution.

### Wilson score lower bound (handles the "2→10 stars = +400%" noise problem directly)

```
lower_bound = (p̂ + z²/2n − z·√(p̂(1−p̂)/n + z²/4n²)) / (1 + z²/n)
```
- `p̂` = proportion (e.g., successes/trials), `n` = sample size, `z` = confidence z-score (1.96 for 95%)
- This is the standard fix for exactly the problem the user named: a ratio-based score (percent change, upvote ratio) is *overconfident* at small `n`. The Wilson lower bound widens the confidence interval as `n` shrinks, which mechanically suppresses a "1 star → 5 stars" (500% growth, n=5) result below a "2,000 → 2,400" (20% growth, n=2000 event-count) result, because the former has far less statistical evidence behind it.
- **Direct implication for this project:** don't rank by raw `%_delta`. Rank by a lower-confidence-bound version of the delta, or equivalently, only compute velocity as a first-class ranking signal once an item clears an **absolute minimum count floor** (below, in Part 2).

### GitHub Trending: not published, but the shape is known

GitHub does not publish the algorithm (confirmed no official spec exists; treat any "exact formula" claim as **LOW confidence** speculation). What's observable and widely corroborated by community reverse-engineering (GitHub Discussions #3083, #163970, multiple blog analyses):
- It is **velocity over an explicit window** (their UI literally exposes "Today / This week / This month" — the window is a first-class dimension, not a hidden constant).
- It is **not** raw star delta — community consensus is it's closer to *stars-gained-relative-to-the-repo's-own-historical-baseline* (a repo normally getting 2 stars/day hitting 10 scores higher than one normally getting 200/day hitting 220), i.e., a per-repo z-score or ratio against trailing average, not a global constant threshold.
- Additional non-star signals (forks, issue/PR activity) are believed to contribute but weighting is unconfirmed.

**What to actually build, since the source is opaque:** treat GitHub Trending as *inspiration for the "window matters" and "compare to own baseline" ideas*, not as a formula to copy. OSS Insight (pingcap's open-source analytics platform, code and docs public) is a better-documented reference: its public formula is `Total Score = Stars score + Forks score + Base score` — a weighted composite rather than pure velocity. This confirms composite scoring (stars + secondary signals) is standard practice among serious OSS ranking tools, not just a nice-to-have.

### Recommended formula for this project

Given the above, and given the specific requirement ("900★ repo gaining 400/week should outrank a dead 40k★ repo, but 2→10★ noise should not"):

```
velocity_score(item) = delta_count(item, window) / max(baseline_avg_delta(item), floor_constant)
```
then rank across sources by **percentile within source-type**, not by raw score, because absolute scales differ (GitHub stars vs HN points vs npm downloads are not comparable units — see normalization below).

Concretely:
1. **Absolute floor** per source type (e.g., GitHub: ignore repos with <20 total stars *and* <5 stars in the window; npm: ignore packages with <100 weekly downloads). This directly kills the "2→10 stars" noise case — it never enters the velocity calculation at all.
2. **Velocity = Δcount over trailing N-day window**, compared against the item's own trailing average (ratio-to-self, like GitHub Trending's presumed approach) *not* a single global multiplier — a repo that normally gains 5 stars/week gaining 50 is a bigger story than one that normally gains 5,000 gaining 6,000, even though absolute deltas differ.
3. **Cross-source normalization via percentile rank, not raw score.** Convert each item's velocity score to a percentile within its own source (e.g., "this repo is in the 95th percentile of GitHub velocity today") rather than comparing raw HN points to raw GitHub stars. Percentile rank is unit-agnostic and is the standard technique for combining heterogeneous scoring signals (used across search/recommendation ranking systems that blend multi-source signals) — MEDIUM confidence, this is a design recommendation synthesizing the researched formulas rather than a directly-cited single source.
4. **Final composite** = weighted blend of normalized velocity percentiles + a small fixed weight for absolute scale (so a 40k★ repo isn't invisible even if flat — it may still be worth a "still relevant" mention, at low priority) — this is what OSS Insight's `stars + forks + base` composite pattern validates as sound practice.

---

## Part 2: Deduplication — Table Stakes, Commonly Underestimated

Real aggregators that solve this (Techmeme, Google News) combine signal matching with human oversight; a single-user local tool can't afford editorial review, so lean fully automated with a conservative merge threshold.

**How Techmeme does it (LOW-MEDIUM confidence — no official spec, pieced together from a 2009 HN thread and secondary sources):** clusters by URL/headline similarity + publication time proximity + named-entity overlap (companies, people, products) + content overlap, then ranks *within* the cluster by source authority and independent-corroboration count, suppressing minor rewrites.

**How generic dedup pipelines work (MEDIUM confidence, cross-referenced across multiple technical sources including a granted patent on news-feed dedup and academic literature):**
1. Embed each item's title+summary (a small embedding model is enough; no need for anything fancy)
2. Compute cosine similarity between same-day items
3. Threshold: **similarity > 0.8** is the commonly-cited cutoff for "same story" in production news-dedup systems
4. Cluster via connected-components or graph-community detection (Leiden algorithm is mentioned as a modern approach) rather than pairwise-only matching, so a 3-way GitHub+HN+changelog cluster merges correctly even if not every pair individually crosses threshold

**For this project specifically, a cheaper approach is available before reaching for embeddings:** entity-anchored matching is enough because the domain is narrow (one repo name / one model name / one release version = one entity). A repo URL (github.com/org/repo) appearing in an HN post title/body and a GitHub trending pull on the same day is a near-certain same-item match — canonicalize on repo URL / package name / release-tag string as the primary dedup key, and fall back to title cosine-similarity only for editorial/discourse items (HN discussion vs. a blog post about the same topic) that don't share a canonical identifier. This is cheaper, more precise, and avoids embedding-model dependency for the majority of items (GitHub release + HN post about that release + changelog entry all carry the same repo URL).

**Merge behavior:** when items merge, keep all source links (a "seen on: GitHub, HN, changelog" indicator is useful signal for the user — corroboration across sources is itself a traction signal, not just noise to collapse away) but only spend one LLM summarization call per cluster, not per source. This also matters for the project's stated cost-control constraint (LLM summarizes only ranking-survivors) — dedup must happen *before* the ranking/summarization gate, not after, or the same story burns 3x the LLM budget.

---

## Part 3: Cold Start — Day 1 With No History

This is a real, unavoidable design problem: velocity is a *derivative* (change over time), and a derivative needs at least two data points. On day 1, there is exactly one snapshot.

**What to do (MEDIUM confidence — synthesizes standard cold-start-in-recommenders patterns, which explicitly list "fall back to popularity/trending-by-absolute-metric" as the standard mitigation, applied to this project's specific shape):**

1. **Day 1 (and until 2+ snapshots exist): fall back to absolute-popularity ranking, clearly labeled as such.** Don't fake a velocity number from a single data point — show raw counts (stars, points) and mark the dashboard state as "baseline day" or similar, so the user isn't misled into thinking day-1 rankings reflect momentum they don't yet have evidence for.
2. **Backfill history where the API allows it.** Several candidate sources expose historical time series directly, which sidesteps cold start entirely for those sources:
   - GitHub: star *history* isn't directly returned by the REST API in one call, but the community pattern (used by star-history.com) is to page through the `stargazers` endpoint with a special media type that returns starred-at timestamps, reconstructing a full historical curve in one pass — this means GitHub velocity does NOT need to wait for day 2; a full backfill is possible on day 1 for any repo.
   - npm/PyPI download counts: their public APIs return historical daily/weekly download series directly (not just current snapshot) — again, no cold-start wait needed.
   - HN: Algolia API returns point/comment counts at query time only (a snapshot), not history — HN velocity **does** have a genuine 2-snapshot cold start.
3. **Once 2+ snapshots exist for a source that can't be backfilled, compute velocity normally but widen the "floor constant" (Part 1) for the first week** — with only 2-3 data points, apply the Wilson-style conservatism more aggressively (treat early velocity numbers as low-confidence and rank them below absolute-popularity items until enough snapshots accumulate to trust the trend).
4. **Practical implication for build order:** the ingestion/snapshot-storage feature must exist before the ranking feature can be meaningfully tested — but the *backfill* capability (point 2) means the "wait several days to have anything useful" failure mode is avoidable for the GitHub and package-registry sources, which is most of the domain's signal. Design the roadmap so backfill-capable sources are wired first, since they make the dashboard useful from day 1 rather than day 7.

---

## Part 4: Noise Control — Filtering, Muting, Seen/Unseen, Decay

Table stakes for any daily-use single-user reading tool, borrowed from RSS-reader design patterns:

- **Read/unread (seen/unseen) state** is the single most load-bearing noise-control feature for a daily-use tool — without it, every day re-shows everything and the tool becomes unusable within a week. This is confirmed as core to virtually every RSS reader design discussion (FreshRSS issue trackers treat read/unread semantics as foundational, not optional).
- **Item decay / aging out**, not just binary read/unread. A well-regarded independent RSS reader ("Current") implements a "river" model where different item types get different lifespans before they fade from view even if unread — breaking news gets ~3 hours of relevance, daily articles ~18 hours, evergreen content up to a week. **Direct analog for this project:** a model-release announcement should decay off the "new today" view faster than a slow-burning framework-adoption trend; different section types plausibly warrant different staleness windows, though this can start as one global window and be refined later.
- **Mute (source or category)** — the ability to say "stop showing me r/LocalLLaMA" or "stop showing me the Safety & guardrails section" without deleting the underlying ingestion pipeline, i.e., mute is a display filter, not a source-removal action. Cheap to build, high value for a single user who will inevitably develop blind spots/preferences over time.
- **"Still relevant" long-tail surfacing** — items that keep clearing the ranking bar day after day (a framework that's been top-ranked for two weeks straight) need *some* signal distinct from "new today," otherwise the dashboard either re-promotes the same item endlessly or the item vanishes the moment its single-day velocity dips. A simple "days consecutively ranked" counter, displayed rather than acted on, is enough for a single user — no need for a complex trend-detection state machine.

---

## Part 5: Source Coverage for the AI-Coding Domain

Building on the candidate list already in PROJECT.md, prioritized by signal-per-effort for this specific narrow domain:

| Source | Signal type | Backfill-capable (cold start)? | Notes |
|---|---|---|---|
| GitHub (stars, via stargazers-timestamp endpoint) | Traction | Yes | Highest-value single source; full history reconstructable in one backfill pass |
| GitHub (releases/changelogs via Releases API) | Releases | N/A (factual events, not counts) | Cheap, structured, no ranking noise — these are binary "did a release happen" events |
| Hacker News (Algolia API) | Discourse + weak traction proxy (points) | No — snapshot only | Free, clean, well-documented API; genuine 2-snapshot cold start applies |
| npm / PyPI download counts | Traction | Yes | Both expose historical daily download series directly |
| Vendor changelogs (Anthropic, OpenAI, Google, Cursor, etc.) | Releases | N/A | Highest-precision signal for "Models & releases" and "Agentic coding tools" sections; near-zero noise, but requires per-vendor scraping/RSS since no unified API exists |
| r/LocalLLaMA, r/ChatGPTCoding | Discourse | No | Reddit's official API pricing/access changes (2023+) make this the most operationally fragile source — verify current terms before building against it; treat as supplementary, not load-bearing |
| arXiv (cs.SE, cs.CL) | Releases (research) | Yes (arXiv API returns full history) | Lower priority — this domain's "traction" signal is dominated by tools/products, not papers, but useful for the RAG & context and Safety sections |
| Product Hunt | Releases + weak traction (upvotes) | Partial | Useful specifically for "Agentic coding tools" and "Agent frameworks" launch-day visibility; upvote counts share the same small-number noise problem as everything else — apply the same floor |
| awesome-lists (curated GitHub lists) | Discovery, not ranking | N/A | Not a ranking signal at all — useful only as a periodic "did we miss a name" backstop, not part of the daily pipeline |
| Medium | Discourse | No | Per PROJECT.md, deliberately deprioritized — no real API, hidden engagement numbers, heavily SEO-farmed in this domain; confirmed low-value, keep as out-of-scope/supplementary-RSS-only per existing decision |

---

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Multi-source ingestion (GitHub, HN, changelogs, registries, RSS) | The entire premise is "don't scroll five feeds separately" | MEDIUM | Each source has its own API shape/auth/rate-limit; budget per-source adapters, not one generic fetcher |
| Deduplication across sources | Same release will hit GitHub, HN, and a changelog same-day; showing it 3x destroys trust in the tool within days | MEDIUM | Canonical-key matching (repo URL / package name / release tag) handles the majority case cheaply; reserve embedding-similarity for cross-source discourse items without a shared identifier |
| Velocity-based ranking (not absolute popularity) | This is the project's entire stated thesis | MEDIUM-HIGH | Needs: historical snapshot storage, per-source floor constants, ratio-to-own-baseline, cross-source percentile normalization |
| Read/unread (seen/unseen) state | Without it the dashboard re-shows everything daily and becomes noise itself | LOW | Simple boolean + timestamp per item; foundational for daily-use tools per RSS-reader precedent |
| Deterministic pre-ranking gate before LLM summarization | Stated cost-control requirement; also just good practice — ranking should be cheap/local, summarization expensive/gated | LOW-MEDIUM | This is a filter step (threshold on the composite velocity score from Part 1), not a separate feature to design from scratch |
| Click-through to original source | Users need to verify/read the primary source, not just trust a summary | LOW | Just needs the canonical URL preserved through dedup/merge |
| Link to official docs/getting-started per tool | Explicitly named in PROJECT.md requirements | LOW-MEDIUM | For GitHub-sourced items, README/homepage URL from repo metadata covers most cases; some manual/curated mapping likely needed for non-GitHub tools (vendor products) |
| Daily scheduled run (no manual refresh) | Stated requirement — value is in a dashboard that's current when opened | LOW-MEDIUM | Depends on OS-level or app-level scheduler; a reliability concern (missed runs on sleep/wake) more than a design concern |
| Section/category assignment (7 fixed sections) | Explicit requirement; also how any tech-radar-style tool organizes browsing | LOW (mechanically) / MEDIUM (accuracy) | LLM classification into a fixed taxonomy is well-trodden; the taxonomy-fit risk (an item with no obvious home) is the real complexity, not the mechanism |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Velocity-first ranking with cross-source normalization | This is the core "better than skimming GitHub Trending" claim — GitHub Trending only sees GitHub, this tool ranks GitHub+HN+npm+changelogs on one comparable scale | HIGH | The percentile-normalization approach (Part 1) is the actual differentiator; without it the tool is just "GitHub Trending plus some RSS," which isn't a differentiator |
| Two-line "what/why it matters" LLM summary per item | Table-stakes for TLDR/Bensbites-style newsletters, but doing it *per-item on a browsable dashboard* rather than a fixed-cadence email is the differentiator vs. those products | LOW-MEDIUM | Straightforward prompt-engineering task once the ranking gate has already limited volume |
| Cross-source corroboration signal ("seen on: GitHub + HN + changelog") | Surfacing *that* something is corroborated across independent sources is itself a stronger traction signal than any single source's number — no competitor named in the brief does this well for the AI-coding niche specifically | LOW | Nearly free once dedup/merge (Part 2) is built — just surface the merged source list instead of discarding it |
| Backfilled history on day 1 for backfill-capable sources | Removes the "wait a week before this tool is useful" tax that most from-scratch trend trackers pay | MEDIUM | Requires per-source backfill logic (GitHub stargazers-timestamp pagination, npm/PyPI historical series) up front rather than only forward-collecting snapshots |
| Narrow, fixed 7-section taxonomy specific to AI/LLM/agentic coding | ThoughtWorks Tech Radar proves a small number of fixed categories (their rings: adopt/trial/assess/hold) makes a landscape scannable in minutes; this project's taxonomy is the same idea applied to a narrower vertical than any general tech-radar tool | LOW (once taxonomy is fixed) | The taxonomy itself was defined in PROJECT.md already — building to it is mechanical; the *research risk* is classification accuracy, tracked as a pitfall, not a features gap |

### Anti-Features (Explicitly Out of Scope for a Single-User Local Tool)

| Feature | Why It Seems Good | Why Problematic Here | Alternative |
|---------|---------------------|-----------------------|-------------|
| Authentication / accounts / multi-user | Standard for any "product" | Single local user, single machine — auth is pure overhead with zero benefit | None needed; if the dashboard is bound to localhost, that's sufficient access control |
| Sharing / public links / newsletter export | Aggregator products (Techmeme, TLDR) exist to be shared/read by many people | This tool's stated purpose is explicitly personal-only; building sharing invites scope creep into "now it needs a design system, a domain, uptime guarantees" | None — if the user later wants to share a finding, copy-paste the link manually; not a product feature |
| Push notifications / alerting | HN, Reddit, Product Hunt all have notification systems; feels "expected" of a trend tool | Contradicts the stated interaction model ("open it once a day"); notifications imply an always-on service and immediately reintroduce the "interrupt-driven feed-checking" problem this tool exists to replace | The daily scheduled ingestion + a dashboard that's simply *current when opened* is the entire interaction model — no push needed |
| Mobile app / responsive-for-phone polish | Every consumer news product has one | Single user, presumably checking from one or two machines they control; mobile-specific work (native app, PWA, responsive breakpoints beyond "doesn't break") is effort with no stated audience | A local web dashboard viewed in a desktop browser is sufficient; if it happens to render on a phone browser, that's incidental, not a requirement |
| Social features (comments, voting, following other users) | HN/Reddit/Product Hunt are built around this | There is exactly one user; there is no "other people" to interact with | None — the read/unread/mute state described in Part 4 covers all the personalization a single user needs |
| Summarizing every collected item every run | Feels more "complete"/thorough | Rejected explicitly in PROJECT.md on cost grounds — LLM spend must stay bounded; most collected items will be below the ranking threshold and never worth reading anyway | Deterministic pre-ranking gate (already a table-stakes feature above) — only summarize survivors |
| X/Twitter as a source | Feels like an obvious "what's trending" signal | Explicitly rejected in PROJECT.md — API cost disproportionate to signal for this domain | Rely on HN + Reddit + changelogs + GitHub for discourse/traction instead |
| Complex trend-detection state machines (e.g., formal "rising/falling/peaked/declining" lifecycle classification per item) | Sounds like it would make the "still relevant" long-tail problem (Part 4) more rigorous | Massive complexity for a single-user tool where a simple "days consecutively ranked" counter, glanced at once a day, delivers the same practical benefit | The lightweight counter described in Part 4 |
| Real-time / streaming ingestion | "Trend tracking" sounds like it should be live | Contradicts "daily ingestion" as already decided in PROJECT.md; a once-a-day-checked dashboard gains nothing from sub-day freshness, and it multiplies rate-limit/cost/complexity concerns for no benefit | Scheduled daily batch pull (already the stated design) |

---

## Feature Dependencies

```
Historical snapshot storage
    └──requires──> nothing (foundational; must exist before velocity can be computed at all)

Velocity-based ranking
    └──requires──> Historical snapshot storage
    └──requires──> Deduplication  (rank merged items once, not per-source duplicates)
    └──enhances──> Deterministic pre-ranking gate (the gate IS the ranking output, thresholded)

Deduplication
    └──requires──> Multi-source ingestion (nothing to dedup with only one source)
    └──enhances──> Cross-source corroboration signal (a differentiator, nearly free once dedup exists)

Cold-start backfill (GitHub stargazers-timestamp, npm/PyPI historical series)
    └──enhances──> Velocity-based ranking (removes the "wait a week" cold-start tax for backfill-capable sources)
    └──conflicts with──> nothing; it's purely additive, but only applies per-source (HN has no backfill path)

Deterministic pre-ranking gate
    └──requires──> Velocity-based ranking (the gate thresholds on the ranking score)
    └──requires──> LLM summarization (the gate exists specifically to bound what reaches this expensive step)

Section/category assignment (7 fixed sections)
    └──requires──> LLM summarization (classification is done by the same LLM call, or a closely adjacent one)

Read/unread + mute + decay (noise control)
    └──requires──> nothing structural; requires only that items have stable identity across runs (a side-effect of Deduplication's canonical-key approach)

Link to official docs per tool
    └──requires──> Multi-source ingestion (needs the repo/product metadata already being pulled)
```

### Dependency Notes

- **Velocity-based ranking requires Historical snapshot storage:** velocity is a derivative; without at least one prior snapshot to diff against, there is no rate to compute. This is the literal cold-start problem from Part 3 and must be designed for from the first ingestion run, not retrofitted.
- **Velocity-based ranking requires Deduplication:** if the same release is counted 3x (GitHub, HN, changelog) as 3 separate low-velocity items instead of 1 merged item with combined signal, the ranking is measuring noise, not the underlying story's actual traction.
- **Deterministic pre-ranking gate requires Velocity-based ranking:** the gate's threshold *is* the velocity/composite score from Part 1 — there's no separate "gating logic" to build beyond "is this item's score above config value X."
- **Cold-start backfill enhances but doesn't block Velocity-based ranking:** the system works without it (falls back to absolute-popularity on day 1 per Part 3), but backfill removes the multi-day wait for sources where it's available (GitHub, npm, PyPI), which is a meaningful quality-of-life win worth sequencing early.
- **Noise control (read/unread/mute/decay) requires stable item identity, not full dedup sophistication:** as long as the same underlying story consistently maps to the same internal ID across daily runs (a natural side effect of canonical-key dedup), "mark as read" and decay windows work correctly even before cross-source similarity-matching is fully built out.

---

## MVP Definition

### Launch With (v1)

- [ ] Multi-source ingestion for GitHub (stars via stargazers-timestamp backfill + Releases API) and Hacker News (Algolia API) — these two alone cover "Traction" and "Discourse" for the highest-signal source pair named in research
- [ ] Historical snapshot storage — foundational, nothing else works without it
- [ ] Canonical-key deduplication (repo URL / release tag matching) — covers the majority same-item case cheaply, defers embedding-based fuzzy matching
- [ ] Velocity scoring with per-source floor constants and ratio-to-own-baseline (Part 1's recommended formula) — the actual thesis of the product
- [ ] Deterministic pre-ranking gate with a configurable threshold — required for cost control per PROJECT.md
- [ ] LLM summarization (two-line what/why) for items clearing the gate
- [ ] LLM section classification into the 7 fixed sections
- [ ] Local web dashboard: browse by section, sort by velocity, click through to source
- [ ] Read/unread state — without this the tool is unusable past day one
- [ ] Daily scheduled run

### Add After Validation (v1.x)

- [ ] Additional sources: npm/PyPI download velocity, vendor changelogs, r/LocalLLaMA + r/ChatGPTCoding — add once the core ranking/dedup/gate pipeline is proven on the initial two sources
- [ ] Embedding-similarity fallback dedup for discourse items lacking a shared canonical identifier (e.g., an HN discussion and a blog post about the same underlying trend, no shared URL) — add once canonical-key dedup's gaps are actually observed in practice, not preemptively
- [ ] Mute (source or section) — add once real usage reveals which sources/sections the user actually wants filtered
- [ ] Cross-source corroboration display ("seen on: X, Y, Z") — trivial addition once dedup/merge exists, but not required for MVP validation
- [ ] "Days consecutively ranked" long-tail counter — add once the "same item resurfaces every day" problem is actually observed

### Future Consideration (v2+)

- [ ] Per-section decay windows (releases decay faster than framework-adoption trends) — defer until the single global decay window proves too coarse in practice
- [ ] arXiv / Product Hunt / awesome-lists sources — lower-priority per Part 5's signal-per-effort ranking; add only if the core sources leave visible gaps
- [ ] Any form of trend-lifecycle classification beyond a simple counter — explicitly listed as an anti-feature; revisit only if the simple counter proves genuinely insufficient after real use

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Velocity-based ranking (core formula) | HIGH | HIGH | P1 |
| Historical snapshot storage | HIGH | LOW-MEDIUM | P1 |
| Canonical-key deduplication | HIGH | MEDIUM | P1 |
| Deterministic pre-ranking gate | HIGH | LOW | P1 |
| LLM summarization + section classification | HIGH | LOW-MEDIUM | P1 |
| Local dashboard (browse/sort/click-through) | HIGH | MEDIUM | P1 |
| Read/unread state | MEDIUM-HIGH | LOW | P1 |
| GitHub + HN ingestion (initial 2 sources) | HIGH | MEDIUM | P1 |
| Cold-start backfill (GitHub/npm) | MEDIUM | MEDIUM | P2 |
| Additional sources (npm, changelogs, Reddit) | MEDIUM | MEDIUM-HIGH | P2 |
| Cross-source corroboration display | MEDIUM | LOW | P2 |
| Mute (source/section) | MEDIUM | LOW | P2 |
| Embedding-similarity dedup fallback | LOW-MEDIUM | MEDIUM | P2 |
| "Days ranked" long-tail counter | LOW | LOW | P3 |
| Per-section decay windows | LOW | LOW-MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | GitHub Trending | Hacker News | This Project |
|---------|--------------|--------------|--------------|
| Ranking basis | Velocity, opaque formula, single source (stars/forks) | Gravity-decay on votes, single source | Cross-source normalized velocity percentile, explicit floor constants |
| Sources combined | GitHub only | HN submissions only | GitHub + HN + npm/PyPI + changelogs + Reddit (phased) |
| Deduplication | N/A (single source, no cross-posting to dedup) | N/A (single source) | Canonical-key matching, cross-source merge |
| Cold start handling | Unknown/undisclosed | N/A (continuously running, no "day 1") | Explicit backfill for GitHub/npm; fallback-to-absolute for HN until 2nd snapshot |
| Summarization | None — just a repo list | None — just a link+title | LLM two-line what/why per surviving item |
| Categorization | By programming language only | None (flat list) | 7 fixed domain-specific sections via LLM classification |
| Noise control | None (just today's list) | Implicit (gravity decay removes old items from view) | Explicit read/unread + planned mute + decay |
| Personalization | None | None | Single-user by design — no need for personalization *algorithms*, but state (read/mute) is inherently personal |

## Sources

- [Reverse Engineering the Hacker News Ranking Algorithm — sangaline.com](https://sangaline.com/post/reverse-engineering-the-hacker-news-ranking-algorithm/) — MEDIUM confidence (cross-checked)
- [How Hacker News ranking algorithm works — Amir Salihefendic, Medium](https://medium.com/hacking-and-gonzo/how-hacker-news-ranking-algorithm-works-1d9b0cf2c08d) — MEDIUM confidence (cross-checked)
- [How Hacker News ranking really works — righto.com](http://www.righto.com/2013/11/how-hacker-news-ranking-really-works.html) — MEDIUM confidence (cross-checked)
- [How Reddit ranking algorithms work — Amir Salihefendic, Medium](https://medium.com/hacking-and-gonzo/how-reddit-ranking-algorithms-work-ef111e33d0d9) — MEDIUM confidence (cross-checked)
- [Deriving the Reddit Formula — Evan Miller](https://www.evanmiller.org/deriving-the-reddit-formula.html) — MEDIUM confidence (cross-checked, canonical source for Wilson score application to ranking)
- [Wilson Score Interval: Formula, Calculator & Examples](https://statisticsfundamentals.com/confidence-intervals/wilson-score-interval/) — MEDIUM confidence
- [Algorithm to detect trending repositories — GitHub Discussions #3083](https://github.com/orgs/community/discussions/163970) — LOW confidence (unofficial/speculative, GitHub does not publish the algorithm)
- [OSS Insight — Repository ranking by stars, docs](https://ossinsight.io/docs/api/collection-repo-ranking-by-stars/) — MEDIUM confidence (documented public methodology, not independently verified against source code)
- [Techmeme — Wikipedia](https://en.wikipedia.org/wiki/Techmeme) — LOW-MEDIUM confidence (Techmeme does not publish its clustering algorithm; pieced together from secondary sources and a 2009 HN discussion thread)
- [ThoughtWorks Technology Radar — FAQ](https://www.thoughtworks.com/en-us/radar/faq) and [Build Your Own Technology Radar](https://www.thoughtworks.com/insights/blog/build-your-own-technology-radar) — HIGH confidence (official first-party documentation)
- [Current — river/decay RSS reader model](https://www.terrygodier.com/current) — MEDIUM confidence, single source but directly describes a shipped design
- [TLDR AI newsletter](https://tldr.tech/ai) and [Ben's Bites](https://news.bensbites.com/) — MEDIUM confidence, describes observed product behavior, not internal methodology
- Cross-cutting dedup technique sources: news-clustering literature (cosine similarity >0.8 threshold, Leiden community detection) — MEDIUM confidence, general pattern not domain-specific
- Cross-cutting cold-start literature (recommender-systems cold start mitigations, popularity fallback) — MEDIUM confidence, general pattern applied by analogy to this domain
- PROJECT.md (project-internal context, source list and taxonomy already decided)

---
*Feature research for: Personal AI/LLM ecosystem trend-tracking dashboard*
*Researched: 2026-07-19*
