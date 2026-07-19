# Pitfalls Research

**Domain:** Personal, locally-run AI/LLM trend-tracking aggregator (multi-source ingestion, velocity ranking, LLM enrichment, single-user dashboard, Windows 11 scheduled)
**Researched:** 2026-07-19
**Confidence:** MEDIUM-HIGH (rate limits and API mechanics verified against official docs; behavioral/UX pitfalls verified against community reporting and published research, not project-specific field data — this project doesn't exist yet)

## Critical Pitfalls

### Pitfall 1: Silent collector failure (the #1 killer)

**What goes wrong:**
A source stops returning real data but the collector doesn't crash — it returns HTTP 200 with an empty array, a changed JSON shape that gets silently parsed into zero items, or an HTML page whose selectors no longer match (GitHub Trending redesigns its DOM without notice; there is no official trending API, so any GitHub-trending signal is scraped HTML by definition and rots on GitHub's schedule, not yours). The daily job "succeeds" — no exception, no non-zero exit code — while quietly ingesting nothing from that source. Weeks later the owner notices a whole section of the dashboard is stale or thin and has to reconstruct when it broke.

**Why it happens:**
Collectors are written to handle the happy path and outright errors (5xx, timeout, connection refused), but not the "silently different" path: 200 OK + empty payload, or 200 OK + payload with an unexpected/missing field. A `try/except` around the network call catches nothing here because nothing throws.

**How to avoid:**
- Every collector run must record, per source, a small structured result: item count fetched, item count after parsing, timestamp, and any zero/near-zero flag — write this to a per-source health log independent of the item store.
- Add a **floor check**: if a source that historically returns N±variance items returns 0 (or drops below some percentage of its trailing 7-run average), flag it loudly — surface it on the dashboard itself (a "collector health" banner/row is cheap and this is a single-user tool, so "loudly" can just mean visible on open, no need for external alerting infra).
- Treat "0 items parsed" as a distinct state from "source unreachable" in logs — they have different root causes and both need to be visible.
- For HTML-scraped sources specifically (GitHub Trending has no API — confirmed above), pin a fixture/snapshot test of the expected DOM shape so a schema change is caught by a broken selector test, not by silent zero output, before it ships to the daily job.

**Warning signs:**
- A source's daily item count trends toward zero over several runs, or drops off a cliff between two consecutive runs with no corresponding real-world event.
- The dashboard "looks the same as yesterday" for one whole section repeatedly.

**Phase to address:**
Collection/ingestion phase — build the per-source health log and floor-check as part of the collector contract from day one, not retrofitted later. This is cheaper to bake in now than to add after three sources have already silently died.

---

### Pitfall 2: Velocity ranking whipsaws on small-number noise and gets gamed by fake stars

**What goes wrong:**
Two failure modes compound: (a) a repo going from 2 to 10 stars in a day is mathematically "+400%" and can rank above a repo going from 4,000 to 4,300 (+7.5%) despite the second being the real traction signal; (b) GitHub star velocity is an actively gamed metric — published 2024/2025 research (StarScout, CMU/Socket/NC State) identified ~6 million suspected fake stars across ~15,800 repos, with fake-star campaigns growing roughly two orders of magnitude in 2024, and documented cases of purchased-star repos successfully reaching GitHub's own Trending page. Velocity-based ranking is *exactly* the metric this fraud targets, and "AI tool" repos are a common target category for this kind of reputation-boosting.

**Why it happens:**
Raw percentage-change ranking has no concept of sample size or statistical confidence, so tiny absolute deltas produce enormous, meaningless ratios. Bot-star farms are specifically optimized to move exactly this kind of metric because it's cheap to fake and highly visible.

**How to avoid:**
- Do not rank by raw percentage delta on small absolute counts. Use an approach with a built-in confidence penalty for low sample size — the standard fix (used by Reddit/HN-style ranking, derived from the Wilson score interval) is to rank by a lower-confidence-bound estimate rather than the raw ratio, so small-n swings get pulled toward zero instead of exploding to +400%.
- Set an absolute minimum-count floor before a delta is eligible to rank at all (e.g., don't compute "velocity" off a base under some threshold like 10-20 stars/downloads — below that, log the item but don't let it win the ranking on ratio alone).
- Treat single-day star bursts with suspicion when the absolute magnitude is unusually large relative to the repo's history — StarScout-style detection (burst clustering, minimal contributor overlap with the rest of the ecosystem) is heavyweight for a personal tool, but a cheap proxy is available: prefer sustained multi-day trend over single-day spike (see Pitfall 3), since manufactured stars are usually a short coordinated burst, not sustained organic growth.

**Warning signs:**
- The top of the dashboard changes dramatically day-to-day for the same handful of low-count repos.
- A previously-unknown, low-activity repo suddenly jumps to #1 on ratio alone with no corresponding HN/Reddit discussion or release note to explain it.

**Phase to address:**
Ranking/scoring phase — the ranking formula itself is the fix; this cannot be patched onto a naive "current minus previous, divided by previous" implementation after the fact without a rewrite.

---

### Pitfall 3: Launch-day spikes and weekend/timezone seasonality break naive day-over-day comparison

**What goes wrong:**
A "Show HN" post, Product Hunt launch, or vendor announcement produces a one-day spike in stars/upvotes/mentions that regresses to near-zero the next day. A pure day-over-day velocity metric puts that item at #1 for exactly one day and then it vanishes — the dashboard "whipsaws." Separately, GitHub star activity, HN submissions, and Reddit posting all have real day-of-week patterns (activity dips on weekends in aggregate, varies by timezone of the dominant audience); comparing Saturday's raw count to Tuesday's raw count treats a seasonal dip as a momentum change.

**Why it happens:**
Single-point-in-time deltas (yesterday vs. today) are the simplest thing to compute and are what most from-scratch trend trackers implement first — they don't account for the fact that "today" and "yesterday" are not interchangeable units when human activity has weekly seasonality, and they don't distinguish a spike from a trend.

**How to avoid:**
- Rank on a multi-day trailing window (e.g., 3-day or 7-day average/slope) rather than a single-day delta, so one spike day gets smoothed rather than dominating.
- If day-of-week normalization matters at this signal size (it likely does for HN/Reddit volume, less so for star counts), compare like-to-like (e.g., this Tuesday vs. last Tuesday, or a 7-day rolling window that naturally spans a full week) rather than adjacent calendar days.
- Consider a decay: an item's rank should fall off over subsequent days after a spike rather than dropping to zero instantly — sustained multi-day interest is the actual "traction" signal the project's Core Value depends on ("what is actually gaining traction," not "what got posted once").

**Warning signs:**
- Same complaint pattern as Pitfall 2 (daily top-of-list churn) but specifically correlated with weekends, or with one-time announcement events rather than ongoing repo activity.

**Phase to address:**
Ranking/scoring phase, same as Pitfall 2 — these two are the same underlying design decision (window size and smoothing function for the velocity metric) and should be solved together, not sequentially.

---

### Pitfall 4: LLM hallucinates confidently about brand-new tools it has stale/no knowledge of

**What goes wrong:**
The entire point of this dashboard is surfacing things that are new *this week*. That is precisely the case where the summarizing LLM's parametric knowledge is weakest or nonexistent — anything released after its training cutoff is unknown territory, and unlike a human, the model has no built-in signal that says "I don't actually know this, I'm guessing." Research on hallucination in LLMs describes exactly this: models show measurable overconfidence on low-familiarity/unknown entities, and generate a fabricated-but-plausible description with the same fluency and tonal confidence as a correct one. Concretely: if the LLM is asked to summarize "what is X" using only its own knowledge (rather than the fetched README/changelog text), it may confidently invent a description of a tool that doesn't match what the tool actually does, especially for anything released in roughly the last 6-18 months relative to its training cutoff.

**Why it happens:**
It's tempting to let the LLM "just summarize what it knows" about a well-known-sounding name, skipping the step of feeding it the actual source text (README, changelog, HN comment) — this is cheaper in tokens and prompt complexity, but for new/obscure tools there is no reliable parametric knowledge to draw on.

**How to avoid:**
- Never let the LLM summarize from its own knowledge alone. Always ground the summarization call in freshly fetched source text (repo README/description, changelog entry, HN/Reddit thread text) passed in the prompt, and instruct it explicitly to summarize *only* the provided text, not what it "knows" about the tool.
- For items where fetched source text is thin (e.g., a bare repo with no README), prefer marking the item as "insufficient info" or falling back to a template-based factual card (name, source link, raw stats) over letting the LLM fill the gap — a bad-but-honest sparse card beats a fluent, wrong one.
- Spot-check: since this is a single-user tool, periodically (e.g., weekly) manually check a handful of summaries for brand-new items against their actual source pages — this is cheap and catches drift before trust in the dashboard erodes.

**Warning signs:**
- A summary reads suspiciously generic/templated for a tool with a very new/unusual name.
- A summary describes capabilities that don't appear anywhere in the linked README or docs.

**Phase to address:**
LLM enrichment phase — this is a prompt-design and data-plumbing decision (always ground on fetched text, never on parametric recall) that must be the default from the first enrichment call, not a later guardrail.

---

### Pitfall 5: LLM classification drift and non-determinism make the dashboard feel unstable

**What goes wrong:**
The same tool gets filed into a different one of the seven sections on different runs (e.g., an MCP server framework classified as "Protocols & interop" one day and "Agent frameworks" the next), or the two-line summary text changes wording day to day for an item whose underlying data hasn't materially changed. Both erode trust — a dashboard that visibly reclassifies or rewords things without a corresponding real-world change reads as unreliable/"random" even when nothing is actually broken.

**Why it happens:**
Borderline items genuinely straddle two of the seven fixed sections (the taxonomy's own "one obvious home" test will fail on some real items — MCP servers *are* both protocol and agent-framework-adjacent). Combined with LLM sampling non-determinism (even at low temperature, repeated calls to the same prompt can produce different classifications for ambiguous inputs), the same item can flip on every run if it's re-classified from scratch each time.

**How to avoid:**
- Classify and summarize once per item, then cache the result keyed to the item's identity (repo/URL) plus a content hash of the input text. Only re-run the LLM call when the underlying source text changes meaningfully — never regenerate on every run "just because."
- Use temperature 0 (or the lowest available) for classification calls specifically — determinism matters more than creativity here.
- For genuinely ambiguous items, prefer a small set of deterministic tie-break rules ahead of the LLM call (e.g., keyword/topic heuristics from the repo's own GitHub topics or package metadata) so borderline cases don't depend on LLM sampling at all.
- If classification does need to change later (e.g., the taxonomy test fails on a real item, per the "revisit if classification error is high" note in PROJECT.md), make it an explicit manual override or a deliberate re-run, not a silent daily re-roll.

**Warning signs:**
- An item's section changes between two consecutive dashboard opens with no corresponding change to the tool itself.
- Wording of a summary changes daily for an otherwise static item.

**Phase to address:**
LLM enrichment phase — caching-by-content-hash and temperature=0 are cheap to build in from the start and expensive to retrofit once the dashboard has "always felt flaky."

---

### Pitfall 6: LLM cost creep on unusual/viral days

**What goes wrong:**
The deterministic pre-ranking threshold (already a planned decision) caps the *rate* at which items reach the LLM under normal conditions, but on an unusual day — a major model launch, a viral HN thread that spawns dozens of related repos, a big vendor announcement cycle — the number of items clearing the threshold can spike far above a typical day, and so does the LLM bill for that run, with no ceiling.

**Why it happens:**
A per-item threshold controls *quality* of what's let through but not *quantity per run*; if 300 items instead of the usual 30 clear the bar on a big news day, the run costs 10x with no circuit breaker.

**How to avoid:**
- Add a hard per-run cap on the number of items sent to the LLM (e.g., top N by pre-ranking score, even if more than N clear the threshold) as a second, independent gate alongside the threshold.
- Log per-run token/cost estimates so a cost spike is visible after the fact even if it's not hard-capped in v1.
- Since summaries are cached (Pitfall 5), a viral item that appears across multiple sources (HN + Reddit + a repo) should be summarized once and referenced from multiple entries, not re-summarized per source mention.

**Warning signs:**
- A single run's LLM spend is a large multiple of the typical run.

**Phase to address:**
LLM enrichment phase — implement the hard cap alongside the threshold gate, not as a follow-up fix after a surprise bill.

---

### Pitfall 7: Scope creep toward "track everything"

**What goes wrong:**
The project's explicit constraint is narrowness (AI/LLM/agentic coding only, seven fixed sections). The natural failure mode for a hobby aggregator is the owner finding one more interesting adjacent thing — a general AI-hardware post, a broader "tech news" item, an interesting non-AI dev-tool release — and wanting to add "just this one source" or "just one more section" to capture it. Each addition individually seems reasonable; cumulatively they turn the seven-section, single-domain tool into an unbounded "track everything" tracker, which is the exact failure PROJECT.md's Out of Scope section is designed to prevent, and which erodes the narrow signal-to-noise ratio that is the whole value proposition.

**Why it happens:**
Curiosity-driven scope creep is the default behavior of a tool built and used by one person for their own interest — there's no second stakeholder pushing back on adding "just one more thing," and the cost of adding a source feels low in the moment even though the cost of the resulting broader/noisier taxonomy is high and compounds.

**How to avoid:**
- Apply the taxonomy test already defined in PROJECT.md ("a new item should have exactly one obvious home") as an admission gate for new *sources*, not just new *items*: if a candidate new source's typical content doesn't map cleanly into one of the existing seven sections, it doesn't get added — expanding the taxonomy is a milestone-level decision, not something that happens implicitly by adding a source.
- Explicitly resist adding an eighth "Misc/Other" section — a catch-all bucket is the standard escape hatch by which scope creep enters through the back door (anything can be justified as "well it sort of fits in Misc").
- Keep the Out of Scope list in PROJECT.md as a living checklist reviewed at milestone boundaries (already the documented process) — re-affirm each exclusion rather than silently letting it lapse.

**Warning signs:**
- A proposed new source or section is justified by "it's related" rather than "it has exactly one obvious home in the existing taxonomy."
- A "Misc" or "Other" section gets proposed.

**Phase to address:**
Applies across all phases as an ongoing discipline, but should be explicitly called out as a non-goal in whichever phase adds the second/third source (so the pattern of "one obvious home or no" is established before it's tested by a tempting exception).

---

### Pitfall 8: Windows Task Scheduler silently fails to run the daily job

**What goes wrong:**
On Windows 11, a laptop/desktop that sleeps overnight commonly does **not** wake to run a scheduled task even when a daily trigger is configured, and this is a widely reported, inconsistent problem (not a one-off misconfiguration) — reports describe the behavior as flatly unreliable across Windows 10 and 11. If the machine is asleep at the scheduled time and wake-related settings aren't explicitly configured, the task simply doesn't run that day — silently, with no dashboard update and no error the owner sees unless they go looking in Task Scheduler's history.

**Why it happens:**
Three separate settings all default to states that produce this failure and all three must be corrected: (1) the task's own "Wake the computer to run this task" option (Conditions tab) is off by default; (2) the power plan's "Allow wake timers" (Power Options → advanced settings → Sleep) is often disabled, especially on laptops with aggressive battery-saving defaults; (3) "Run task as soon as possible after a scheduled start is missed" (Settings tab) is off by default, so a missed run due to the machine being off/asleep at the trigger time doesn't get made up later — the job just doesn't run until the next scheduled trigger.

**How to avoid:**
- Explicitly enable all three settings above when creating the scheduled task, not just the trigger time.
- On the dashboard itself, surface "last successful run" timestamp prominently (this doubles as the health-check surface for Pitfall 1) so a missed run is visually obvious the moment the owner opens the dashboard, rather than requiring them to dig into Windows Task Scheduler's history.
- Consider a lightweight self-healing behavior: on dashboard open, if the last run is older than the expected cadence (e.g., >36h for a daily job), trigger a catch-up run rather than waiting for the next scheduled trigger.

**Warning signs:**
- "Last updated" timestamp on the dashboard is older than expected when opened.
- Task Scheduler's history shows missed/skipped triggers.

**Phase to address:**
Scheduling/ops phase — configure all three wake-related settings as part of setup, and add the "last successful run" indicator to the dashboard in the same phase the scheduler is wired up (it's cheap now, expensive to retrofit once "why is this stale" becomes a recurring mystery).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Let LLM classify/summarize from its own knowledge instead of fetched source text | Simpler prompt, fewer tokens fetched per item | Confident hallucination on new tools (Pitfall 4) — undermines the exact use case | Never |
| Re-run LLM classification/summarization on every daily pass instead of caching by content hash | Simpler pipeline, no cache invalidation logic | Non-determinism visibly reclassifies/rewords items daily (Pitfall 5); wasted spend | Only for a throwaway prototype, never past first real run |
| Rank by raw day-over-day percentage delta | Trivial to implement first | Small-number noise and single-day spikes dominate the list (Pitfalls 2–3) | Acceptable for a one-day spike/demo, not for the shipped ranking |
| Scrape GitHub Trending HTML directly with no fixture/schema test | Fast to stand up, no API auth needed | Breaks silently on GitHub's next redesign, discovered weeks later (Pitfall 1) | Acceptable only if paired with a floor-check/health-log from day one |
| Skip a per-source health log, rely on "no exception = success" | Less code to write initially | Silent collector failure is undetectable until a section goes visibly stale (Pitfall 1) | Never |
| Use unauthenticated GitHub API calls | No token setup needed | 60 req/hour ceiling (vs. 5,000 authenticated) is exhausted almost immediately by any multi-repo velocity check | Never for this project — always authenticate |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| GitHub REST API | Using unauthenticated requests (60/hour) or hitting the general 5,000/hour core limit with the stricter Search API (30/min authenticated, far less unauthenticated) | Always authenticate with a personal access token; treat Search API as its own, much stricter budget separate from the core API; use conditional requests (`If-None-Match` with the returned `ETag`) so unchanged resources return 304 and don't count against the primary limit |
| GitHub Trending | Treating it as a stable data source with a documented API | There is no official trending API — this is DOM-scraped by every tool that offers it; pin fixture tests on the expected structure and treat this source as the most likely to silently break |
| Hacker News (Algolia API) | Polling in a tight loop assuming "no documented limit" means "unlimited" | No hard published rate limit for read-only use, but cache aggressively and back off; on a 429, wait ~60s before retry; a daily-cadence tool needs at most a handful of requests, so this is low-risk if not hammered |
| Reddit API | Assuming free, unauthenticated, high-volume access still works post-2023 pricing changes | Register an OAuth app; expect 100 QPM (OAuth) vs. 10 QPM (non-OAuth) limits per Reddit's published figures, and be aware of the November 2025 "Responsible Builder Policy" requiring pre-approval and prohibiting commercial use — a personal single-user project should qualify as non-commercial, but confirm current terms before depending on Reddit as a primary source, since Reddit's pricing changes have already killed multiple established third-party clients |
| npm registry | Polling every package's metadata individually at high frequency | Use the bulk downloads endpoint (capped at 128 packages / 365 days per query) where possible; set a descriptive User-Agent; treat "acceptable use" as a real policy — npm has throttled/blocked high-volume automated callers without warning in the past |
| PyPI JSON API | Making rapid bursts of requests with a generic/default User-Agent | Set a unique, contact-identifying User-Agent per PyPI's own guidance; respect `ETag`/conditional requests; avoid thousands of requests in a short window even though no hard rate limit is currently enforced at the edge — PyPI reserves the right to block irresponsible callers |
| Vendor changelogs / RSS | Assuming RSS feed structure/URL is permanent | Same silent-rot risk as HTML scraping — apply the same health-log/floor-check pattern from Pitfall 1 |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Re-summarizing/re-classifying every item on every run | LLM cost scales with total tracked items, not new/changed items; daily bill keeps climbing as the tracked set grows | Cache by content hash; only call the LLM on new items or meaningfully changed source text | Noticeable once the tracked backlog exceeds ~100-200 items, since most won't have changed day to day |
| No per-run cost/item cap | A single viral news day (major model launch, big HN thread) spikes LLM spend far above typical | Hard cap on items sent to LLM per run, independent of the ranking threshold | First unusual news day after launch |
| Polling every source at the same fixed interval regardless of source volatility | Wastes request budget on slow-moving sources (vendor changelogs, RSS) while potentially under-polling fast-moving ones (HN front page) | Tune polling cadence per source type; daily cadence is likely sufficient for all sources given the project's own "check once a day" usage model — no need to over-poll | Not a near-term risk for a daily-cadence single-user tool, but worth deciding deliberately rather than defaulting to one interval for everything |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Committing API tokens (GitHub PAT, Reddit OAuth secret, LLM API key) into the repo or config file tracked by version control | Credential leak, quota abuse by others, unexpected billing on the LLM key | Store secrets in an untracked `.env`/local config; never write tokens into any file in the git tree |
| Rendering LLM-generated summaries or scraped titles directly into the dashboard HTML without escaping | Stored XSS from a malicious/crafted repo name, HN title, or README content designed to inject script (low likelihood but non-zero given fake-star/spam campaigns actively target GitHub's discovery surfaces) | Escape/sanitize all externally-sourced text before rendering, even though this is a single-user local tool — defense in depth costs little here |
| Trusting fetched HTML/README content as safe to pass unmodified into the LLM prompt | Prompt injection from a malicious repo README instructing the summarizer to ignore instructions or misrepresent the tool | Treat all fetched source text as untrusted input in the prompt; keep the summarization instruction structurally separate from the fetched content (e.g., clear delimiters) |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Daily top-of-list churn from noisy velocity ranking (Pitfalls 2-3) | Owner stops trusting the ranking, reverts to scrolling raw feeds — defeats the tool's purpose | Smoothed, confidence-aware ranking (Wilson-style lower bound, multi-day window) as described above |
| No visible indicator of stale/failed collection (Pitfall 1, 8) | Owner assumes "nothing happened in this section" rather than "the collector broke" — wrong conclusion, wasted trust | Per-source "last updated"/health indicator on the dashboard itself |
| Section reclassification flicker (Pitfall 5) | Dashboard feels arbitrary/unreliable even when data is technically correct | Cache classifications; change them only deliberately |
| No way to dismiss/mark an item as "already seen, not interesting" | Dashboard re-surfaces the same known items daily, reintroducing scroll-fatigue the tool exists to eliminate | Simple seen/dismissed state per item, since this is explicitly a "5 minutes, know what's new" tool per PROJECT.md's Core Value |

## "Looks Done But Isn't" Checklist

- [ ] **Collectors:** Often missing a per-source health/heartbeat log — verify each source records item-count-over-time somewhere independent of the item store itself, not just "did the HTTP call succeed."
- [ ] **Ranking:** Often missing a minimum-absolute-count floor before percentage-based velocity applies — verify a 2→10-star item cannot outrank a 4,000→4,300-star item on ratio alone.
- [ ] **LLM enrichment:** Often missing grounding-on-fetched-text — verify the summarization prompt actually includes fetched README/changelog/thread text and instructs the model to use only that, not its own recall.
- [ ] **LLM enrichment:** Often missing a cache keyed by content hash — verify re-running the daily job twice in a row does not re-summarize/re-classify unchanged items or incur LLM cost twice.
- [ ] **Scheduler:** Often missing wake-from-sleep configuration — verify "Wake the computer to run this task," "Allow wake timers," and "Run task as soon as possible after a missed start" are all explicitly set, not left at Windows defaults.
- [ ] **Dashboard:** Often missing a "last successful run" / collector-health indicator — verify staleness is visible without opening Task Scheduler or log files.
- [ ] **GitHub integration:** Often missing authenticated requests — verify a PAT is used and that Search API usage (much stricter limit) is tracked separately from core API usage.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|-----------------|
| Silent collector failure discovered weeks later | MEDIUM | Backfill is often impossible (source's own "new since X" window may have already passed, e.g., HN front page); accept the gap, fix the collector, add the health-log/floor-check retroactively so it can't recur silently again |
| Naive velocity ranking already shipped and trust is eroding | LOW | Ranking formula is swappable independent of collected data — historical raw counts are still there; replace the ranking function without needing to re-collect anything |
| LLM classification drift already visible to the owner | LOW | Add the content-hash cache; on next run, re-classify everything once (one-time cost) and cache from then on |
| Windows scheduled task has been silently skipping runs | LOW | Fix the three wake/missed-run settings; add the "last successful run" dashboard indicator so recurrence is caught immediately instead of discovered incidentally |
| Fake-star-inflated item made it into the dashboard as "top trending" | LOW | No automated fix needed for a personal single-user tool at this scale — spot-correct manually if noticed; if it becomes frequent, add the sustained-multi-day-trend preference described in Pitfall 2 |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|---------------|
| Silent collector failure (#1) | Collection/ingestion phase | Per-source health log exists; a source manually forced to return 0 items triggers a visible flag |
| Small-number noise / fake stars (#2) | Ranking/scoring phase | A synthetic 2→10-star item does not outrank a synthetic 4,000→4,300-star item in the ranking output |
| Launch-day spikes / seasonality (#3) | Ranking/scoring phase (same as #2) | A synthetic one-day spike item's rank decays over the following days rather than staying pinned at #1 then vanishing |
| LLM hallucination on new tools (#4) | LLM enrichment phase | Summarization prompt inspected/tested to confirm it is grounded in fetched source text, not model recall alone; a test item with a fabricated/unusual name produces a summary that only reflects the fetched text |
| Classification drift / non-determinism (#5) | LLM enrichment phase | Running the same item through the pipeline twice produces an identical section assignment and cached summary (no re-call) |
| LLM cost creep on viral days (#6) | LLM enrichment phase | A synthetic run with an unusually large number of qualifying items is capped and doesn't exceed a defined per-run budget |
| Scope creep (#7) | Ongoing, established at second/third source addition | Any proposed new source or section is checked against the "one obvious home" taxonomy test before being added |
| Windows Task Scheduler silent failure (#8) | Scheduling/ops phase | Wake timers, wake-the-computer, and run-if-missed settings are all explicitly configured; dashboard shows last-successful-run timestamp |

## Sources

- [GitHub Docs: Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) — HIGH (official)
- [GitHub Docs: Best practices for using the REST API](https://docs.github.com/rest/guides/best-practices-for-using-the-rest-api) — HIGH (official)
- [GitHub Changelog: Updated rate limits for unauthenticated requests (2025-05-08)](https://github.blog/changelog/2025-05-08-updated-rate-limits-for-unauthenticated-requests/) — HIGH (official)
- [GitHub Docs: REST API endpoints for rate limits](https://docs.github.com/en/rest/rate-limit/rate-limit) — HIGH (official)
- [PyPI Docs: API introduction/etiquette](https://docs.pypi.org/api/) — HIGH (official)
- [npm blog: Avoiding the Tragedy of the Commons — Acceptable Use of the Public Registry](https://blog.npmjs.org/post/187698412060/acceptible-use.html) — HIGH (official)
- [npm blog: API rate limiting rolling out](https://blog.npmjs.org/post/164799520460/api-rate-limiting-rolling-out.html) — HIGH (official)
- [Hacker News official API repo](https://github.com/HackerNews/API) and [HN Algolia Search API](https://hn.algolia.com/api) — MEDIUM-HIGH (official/quasi-official; no formally documented hard rate limit for read use)
- [Six Million (Suspected) Fake Stars on GitHub (ICSE 2026 paper, CMU/StruDeL)](https://cmustrudel.github.io/papers/icse2026fakestars.pdf) — HIGH (peer-reviewed research)
- [4.5 Million (Suspected) Fake Stars in GitHub (arXiv 2412.13459)](https://arxiv.org/html/2412.13459v1) — HIGH (research preprint)
- [Dagster: Detecting Fake GitHub Stars](https://dagster.io/blog/fake-stars) — MEDIUM (engineering blog referencing the research above)
- Wilson score interval ranking method (Evan Miller's widely-cited "How Not To Sort By Average Rating" approach, referenced across multiple statistics explainer sources) — MEDIUM-HIGH (well-established, widely reused technique, not a single primary source)
- Reddit API pricing/rate-limit figures ($0.24/1K commercial, 100 QPM OAuth free tier, 10 QPM non-OAuth, Nov 2025 Responsible Builder Policy) — MEDIUM (aggregated from multiple third-party developer-blog summaries in 2026; Reddit does not publish a single canonical rate card, so treat exact figures as directionally correct and verify against Reddit's current developer terms before depending on this source)
- Windows Task Scheduler wake-from-sleep reliability reports (Microsoft Q&A community threads, multiple independent reports across Win10/Win11) — MEDIUM (community-reported, consistent across many independent threads, not an official Microsoft admission of a defect)
- LLM hallucination on unknown/post-cutoff entities (general survey/explainer sources on hallucination causes) — MEDIUM (well-established phenomenon in LLM literature, sourced from secondary explainers rather than a single primary benchmark for this exact scenario)
- Personal dashboard abandonment patterns — LOW-MEDIUM (general productivity-blog commentary, not domain-specific research on aggregator tools specifically; treated here as directionally useful pattern-matching, not a hard citation)

---
*Pitfalls research for: personal AI/LLM trend-tracking dashboard*
*Researched: 2026-07-19*
