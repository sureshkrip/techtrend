# Phase 3: Source Breadth — Discourse, Downloads & Changelogs - Research

**Researched:** 2026-08-19
**Domain:** Multi-source collector plugin extension (Hacker News, npm/PyPI, RSS changelogs) over an existing GitHub-only pipeline
**Confidence:** HIGH (codebase seam), MEDIUM (external API shapes, cross-checked live), LOW (metric-floor calibration, XXE posture)

## Summary

The collector-plugin seam (`base.py`/`registry.py`/`normalize.py`) is genuinely source-blind and works exactly as advertised for adding new `Collector` implementations — that part of COLL-06 is real. **The one place it is NOT source-blind today is the scorer's window-gain reader.** `score.py::compute_window_gain` hardcodes `WHERE ... metric_name = 'stars'` as a SQL literal (score.py:103-104) — it is not parameterized by source at all. Every HN/npm/PyPI/changelog entity will collect cleanly, resolve to an entity, and get snapshot rows written under `metric_name='points'|'downloads'|'releases'` — and then silently score `gain=0, total=0, window_days_actual=0` forever, because `compute_window_gain` only ever looks for rows named `'stars'`. This is not a converter problem (`normalize.py`'s `momentum_for_source` never sees raw snapshot rows — it only receives whatever `(gain, total)` `compute_window_gain` already computed), so **no amount of converter-writing in `normalize.py` alone fixes this.** A small, mechanical parameterization of `score.py` is unavoidable if HN/npm/PyPI/changelog entities are to rank at all. This must be documented as an honest, scoped deviation from COLL-06/SC3 — mirroring the project's existing SQLite→Postgres supersession precedent — not silently absorbed.

The dashboard has a matching, smaller issue: `queries.py`'s `stars_total` correlated subquery and `SORT_KEYS['stars']` are also hardcoded to `metric_name = 'stars'`, and `table.html` literally labels columns "Stars gained" / "Stars". Once the scorer fix lands, `scores.stars_gained` (used for the "Stars gained" column and the `gained` sort) becomes source-agnostic automatically (it stores whatever the entity's own primary metric's window delta was) — but the "Stars" total column will render `—` for every non-GitHub row (harmless, template already handles `NULL`), and both header labels will read misleadingly for non-GitHub rows. This is the "small, honest label-generalization deviation" CONTEXT.md anticipated; it is real, and it does technically touch `techtrend/web/templates/partials/table.html`.

A second, non-CONTEXT-flagged seam gap: `techtrend/collectors/http.py::build_client()` unconditionally requires `GITHUB_TOKEN` and attaches `Authorization: Bearer <token>` — it cannot be reused as-is by HN/npm/PyPI/changelog collectors, all of which are unauthenticated public APIs. New collectors need either their own lightweight `httpx.Client` or a small parameterization of `build_client()`.

**Primary recommendation:** Build the three collectors exactly per CONTEXT.md's discretion notes (Algolia HN Search API, npm/PyPI downloads REST APIs, `feedparser` over curated GitHub Releases Atom + vendor RSS feeds), but budget one small, explicit `score.py` change (a per-source metric-name lookup) and one small `table.html`/`queries.py` label/column touch as part of this phase's plan — not as a silent scope-creep, but as a named, documented deviation the same way the project already documents the SQLite→Postgres reversal.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HN/npm/PyPI/changelog fetch + normalize | Ingestion (collectors) | — | Pure `Collector` protocol implementations, no DB access (matches `GitHubCollector`) |
| Curated source lists (keywords, package names, feed URLs) | Config (`tracked.toml` + `config.py`) | — | D3-4 locked decision; hand-curated, not auto-derived |
| Snapshot persistence | Pipeline / DB (`snapshot.py`, `orchestrator.py`) | — | Already fully source-agnostic; no change needed |
| Per-source metric selection for window-gain | Pipeline / Scoring (`score.py`) | Pipeline / Normalize (`normalize.py`) | **Not source-agnostic today** — `compute_window_gain` hardcodes `'stars'`; needs a small per-source metric-name lookup, naturally colocated next to `normalize.py`'s `_CONVERTERS` |
| Cross-source momentum comparability | Pipeline / Normalize (`normalize.py`) | — | `_CONVERTERS` seam; D-13 says identity-map, don't calibrate yet |
| Dashboard column semantics | Web (`queries.py`, `table.html`) | — | Currently GitHub-star-specific in both SQL and template text; needs label generalization for multi-source rows |

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D3-1 Scope:** Build Hacker News, npm/PyPI, and vendor changelogs in this phase. Three collector modules (npm + PyPI may share one module or be two — planner's call), each registered + given a `normalize.py` converter.
- **D3-2 Cross-source dedup: DEFERRED (separate rows for v1).** Each source produces its own entity. COLL success-criterion 2 (same release resolving to one entity) is explicitly descoped to a follow-up. Record this descope honestly in REQUIREMENTS/ROADMAP.
- **D3-3 Changelog ranking: releases-in-window as momentum.** Count releases within the trailing window and feed that through a `normalize.py` converter as the `(gain, total)` pair — existing velocity model, no scorer change (in intent — see Finding 1 for why a scorer touch is unavoidable regardless of source). Metric key: `{"releases": <count>}`.
- **D3-4 Source lists: curated in `config/tracked.toml`.** HN keywords, npm/PyPI packages, changelog feed URLs are hand-curated, validated through `techtrend/config.py`. NOT auto-derived from tracked GitHub repos.

### Claude's Discretion
- HN collector: Algolia HN Search API, query by AI/LLM keywords (reuse/extend `[discovery].keywords`). Primary momentum signal = story points (comments optional/secondary). No historical backfill exists → HN sparse for the first ~week, matching GitHub's D-08a honesty.
- npm/PyPI collectors: npm downloads via `api.npmjs.org/downloads/`, PyPI via pypistats API. Metric = `{"downloads": N}`; momentum = downloads gained over the window.
- Changelogs: `feedparser` over curated RSS/Atom feed URLs; each feed entry within the window counts as a release. Entity `full_name` from the feed/config label.
- npm/PyPI as one "packages" collector vs. two — planner's call.

### Deferred Ideas (OUT OF SCOPE)
- Cross-source identity resolution / dedup (COLL SC2) — deferred per D3-2; separate rows per source for v1.
- Real cross-source momentum calibration — per D-13, converters stay near-identity until there is observed points/downloads/releases data to calibrate against.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COLL-03 | System collects stories and points from the Hacker News Algolia API | HN section below: verified live endpoint, field shapes, rate limit |
| COLL-04 | System collects package download counts from npm and PyPI | npm/PyPI section below: verified endpoints, response shapes, caveats |
| COLL-05 | System collects vendor release notes from configured RSS/Atom changelog feeds | Changelog section below: `feedparser`, verified working feed URLs, entry-window counting pattern |

Note: COLL-06 ("no changes to scoring, enrichment, or dashboard code") is already marked `[x]` complete from Phase 1, but that claim was only ever exercised with a single source (GitHub). Finding 1 and Finding 2 below show it does not hold once a second source with a different metric name is added — flag for the planner/discuss step to re-open and document, not silently re-mark complete.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| `feedparser` | 6.0.14 (verified via `pip index versions`, PyPI, 2026-08-19) | Parse RSS/Atom changelog feeds | Already named in CLAUDE.md's supporting-libs table; de facto standard Python feed parser, handles malformed feeds gracefully (`bozo` flag) |
| `httpx` | 0.28.1 (already installed) | HTTP calls to Algolia HN, npm, pypistats | Already the project's HTTP client; no new dependency needed |
| `tenacity` | 9.1.4 (already installed) | Retry/backoff on the new HTTP calls | Same `is_retryable`-style predicate pattern as GitHub, reused |

No other new dependencies are required — HN/npm/PyPI are plain JSON REST APIs reachable with the existing `httpx` client.

**Installation:**
```bash
uv add feedparser==6.0.14
# or: pip install "feedparser==6.0.14"
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `feedparser` | Hand-rolled `xml.etree` parsing | Loses `bozo`-flagged malformed-feed tolerance and RSS/Atom format normalization for free; not worth it for 3-8 curated feeds |
| Unofficial vendor blog RSS mirrors (e.g. `tim-hilde.github.io/anthropic-rss`) | GitHub's native `/releases.atom` feeds | GitHub releases Atom feeds are official, first-party, and verified live (see Changelog section) — prefer these over third-party unofficial mirrors for reliability |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `feedparser` | PyPI | Reported "too-new" by the automated heuristic (publishedAt reflects the *latest release date*, 2026-07-30, not package origin) | Not reported (`weeklyDownloads: null`) | `github.com/kurtmckee/feedparser` | **SUS** (heuristic flag) | Flagged — planner should add `checkpoint:human-verify` before install, but treat as very likely a false positive: `pip index versions feedparser` independently shows continuous releases back to `4.1`, the project's own CLAUDE.md already names `feedparser` as the recommended supporting library, and it is the long-standing, canonical "Universal Feed Parser" package with an active, identifiable maintainer repo |

**Packages removed due to `[SLOP]` verdict:** none
**Packages flagged as suspicious `[SUS]`:** `feedparser` — see disposition above; recommend the planner add a lightweight human-verify checkpoint (confirm `pip show feedparser` / PyPI page shows `kurtmckee/feedparser`) rather than treating this as a real risk signal, since independent evidence (version history depth, CLAUDE.md's own prior recommendation) strongly contradicts "too-new."

## Architecture Patterns

### System Architecture Diagram

```
                 ┌─────────────────────────────────────────────────────────┐
                 │                  orchestrator.run_collection             │
                 │        (iterates COLLECTORS, never branches on source)   │
                 └─────────────────────────────────────────────────────────┘
                       │                │                │              │
        ┌──────────────┘        ┌───────┘        ┌───────┘      ┌───────┘
        ▼                       ▼                ▼              ▼
 GitHubCollector          HNCollector      NpmCollector   ChangelogCollector
 (existing)               (new)            PyPiCollector   (new)
 fetch()->raw dicts       fetch()->raw     (new)           fetch()->raw
 normalize()->             fetch()/       fetch()->raw     normalize()->
  CollectedItem            normalize()     normalize()->    CollectedItem
  metrics={stars,           ->             CollectedItem     metrics={releases}
  releases}                CollectedItem   metrics={downloads}
                            metrics={points}
        │                       │                │              │
        └──────────────┬────────┴────────┬───────┴──────┬───────┘
                        ▼                 ▼              ▼
              resolve_entity()   write_snapshot() per metric in item.metrics
              (keys on source, source_native_id — separate rows per source, D3-2)
                        │
                        ▼
              snapshots table (metric_name = 'stars'|'points'|'downloads'|'releases')
                        │
        ⚠ GAP ─────────┤  compute_window_gain() hardcodes metric_name='stars'
                        │  (score.py:103-104) — does NOT read this table
                        │  source-agnostically today
                        ▼
              score.py::rescore_all → scores table (wilson_lower_bound, eligible)
                        │
        ⚠ GAP (minor) ─┤  queries.py's stars_total subquery + table.html labels
                        │  are also 'stars'-specific
                        ▼
              dashboard (server/queries.py + web/templates)
```

### Recommended Project Structure
```
techtrend/collectors/
├── base.py            # unchanged — Collector protocol, CollectedItem
├── registry.py         # +4 lines: HNCollector, NpmCollector, PyPiCollector, ChangelogCollector
├── github.py           # unchanged
├── hn.py               # NEW — Algolia HN Search API collector
├── packages.py          # NEW — NpmCollector + PyPiCollector (two classes, one module)
├── changelog.py         # NEW — feedparser-based ChangelogCollector
└── http.py             # small parameterization: build_client(headers=None, require_github_auth=True)

techtrend/pipeline/
├── normalize.py         # +3 converter classes (identity-mapping, D-13) + PRIMARY_METRIC lookup
└── score.py             # compute_window_gain(conn, entity_id, window_days, metric_name) — parameterized

techtrend/
└── config.py            # +3 Pydantic models: HackerNews, Packages, ChangelogFeed/Changelogs

config/tracked.toml       # + [hn], [packages], [[changelogs]] sections

tests/fixtures/
├── hn/search_response.json
├── packages/npm_downloads.json
├── packages/pypi_recent.json
└── changelog/sample_feed.xml
```

### Pattern 1: New source module mirrors `github.py`'s shape exactly
**What:** Each new collector is a class with `source_id: str`, `fetch(since: date) -> list[dict]`, `normalize(raw: dict) -> CollectedItem`. No DB access inside collectors — matches the existing `GitHubCollector`, which also ignores its `since` parameter in practice (it always fetches "current state," not an incremental delta). New collectors following the same pattern (ignoring `since`, always fetching current values) is consistent, not a new deviation.
**When to use:** All three new sources.
**Example (HN, illustrative):**
```python
# Source: pattern mirrors techtrend/collectors/github.py structure
class HNCollector:
    source_id = "hn"

    def fetch(self, since: date) -> list[dict]:
        config = self._config or load_config()
        client = self._client or _build_public_client()
        hits: dict[str, dict] = {}
        for keyword in config.hn.keywords:
            page = _search_page(client, keyword, config.hn.lookback_days)
            for hit in page.get("hits", []):
                hits[hit["objectID"]] = hit
        return list(hits.values())

    def normalize(self, raw: dict) -> CollectedItem:
        return CollectedItem(
            source=self.source_id,
            source_native_id=str(raw["objectID"]),
            full_name=raw["title"],
            url=raw.get("url") or f"https://news.ycombinator.com/item?id={raw['objectID']}",
            metrics={"points": raw.get("points", 0) or 0},
            discovery_method="hn-search",
        )
```

### Pattern 2: Per-source primary-metric lookup, colocated with the converter seam
**What:** `normalize.py` already owns "how does this source's raw metric become comparable." Add a small sibling lookup so `score.py` knows *which* `metrics` key is the one to window-gain over, per source.
**Example:**
```python
# techtrend/pipeline/normalize.py — new addition alongside _CONVERTERS
PRIMARY_METRIC: dict[str, str] = {
    "github": "stars",
    "hn": "points",
    "npm": "downloads",
    "pypi": "downloads",
    "changelog": "releases",
}


def primary_metric_for_source(source: str) -> str:
    """Which snapshots.metric_name row compute_window_gain should read for
    this source. Falls back to 'stars' for an unrecognized source, matching
    momentum_for_source's own fallback-to-identity behavior.
    """
    return PRIMARY_METRIC.get(source, "stars")
```
```python
# techtrend/pipeline/score.py — compute_window_gain signature change
def compute_window_gain(conn, entity_id: int, window_days: int, metric_name: str) -> WindowGain:
    rows = conn.execute(
        """
        SELECT collected_at, metric_value FROM snapshots
        WHERE entity_id = %s AND metric_name = %s
        ORDER BY collected_at ASC
        """,
        (entity_id, metric_name),
    ).fetchall()
    ...

# rescore_all:
for entity in entities:
    metric_name = primary_metric_for_source(entity["source"])
    gain = compute_window_gain(conn, entity["id"], window_days, metric_name)
    ...
```
This is a mechanical signature/query-literal change only. The Wilson lower-bound math, the floor-before-bound ordering (SCORE-03), and the `WR-03` last-minus-first gain semantics are all untouched.

### Anti-Patterns to Avoid
- **Calling `techtrend.collectors.http.build_client()` unmodified from a new collector:** it unconditionally raises `MissingGithubTokenError` if `GITHUB_TOKEN` is unset and always attaches a GitHub bearer token — wrong for public, unauthenticated APIs. Either give new collectors their own minimal `httpx.Client()` (simplest, no caching) or parameterize `build_client(headers: dict | None = None, require_github_auth: bool = True)` so GitHub keeps its default behavior and new collectors opt out. Either choice keeps the literal string `GITHUB_TOKEN` confined to `http.py`, satisfying the existing T-01-12 confinement grep.
- **Feeding a rate-shaped metric through the scorer as if it were a cumulative counter without checking the math:** see Common Pitfall 1 below — this looked like a landmine during research but the delta math actually still works; don't skip the reasoning, just don't assume it's broken either.
- **Treating `momentum_for_source`/`_CONVERTERS` as the seam that fixes source-blindness in scoring.** It only ever receives an already-computed `(gain, total)` pair; it cannot repair a wrong `metric_name` query that happened upstream of it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| RSS/Atom parsing | Custom `xml.etree`/regex feed parser | `feedparser` | Handles malformed/non-conformant feeds (`bozo` flag), normalizes RSS 2.0 vs Atom field names (`published`/`updated`) into one API |
| HTTP retry/backoff for the 3 new sources | New bespoke retry loops | Same `tenacity` decorator pattern as `github.py`'s `_RETRY_KWARGS`, with a source-appropriate `is_retryable` predicate (public APIs: retry on 5xx and 429, not on 403/404) | Consistency + already-proven pattern in this codebase |
| Package existence/download queries | Scraping npmjs.com or pypi.org HTML | `api.npmjs.org/downloads/*` and `pypistats.org/api/*` — both official, documented JSON APIs | Purpose-built, stable, no scraping fragility |

**Key insight:** The actual hard problem in this phase is not the external API calls (all three are simple, well-documented JSON/XML endpoints) — it is the internal seam gap in `score.py`. Do not let the external-API work distract from budgeting time for the scorer parameterization.

## Common Pitfalls

### Pitfall 1: Assuming every source's metric is a monotonic cumulative counter like GitHub stars
**What goes wrong:** `compute_window_gain`'s `stars_gained = values[-1] - values[0]` assumes the stored `metric_value` is a running total that only grows (WR-03's whole point). GitHub stars and GitHub releases (all-time paginated count) are both naturally cumulative. HN points are effectively stable-per-story once a story ages off the front page, so this also behaves reasonably. **npm/PyPI daily download counts are NOT cumulative** — a raw "last-day downloads" figure resets every day and is a rate, not a running total.
**Why it happens:** It's tempting to snapshot whatever the API's smallest natural unit is (`last-day` downloads) without checking whether the existing last-minus-first gain math still means anything for that shape of data.
**How to avoid:** Snapshot the API's **rolling `last-week` total** (npm: `downloads/point/last-week/{pkg}`; PyPI: `pypistats` `recent.last_week`) as the daily `metric_value`, not the raw daily count. A `window_days=7` last-minus-first delta over 7 daily snapshots of a 7-day rolling total is then a legitimate (if slightly overlapping) week-over-week momentum comparison — directionally sound, not noise. The same reasoning applies to changelog "releases in the trailing window": snapshot the count of feed entries within the lookback window as of that day, not an all-time cumulative count, and let the existing delta math derive "did release velocity change."
**Warning signs:** If a new source's `stars_gained`-equivalent number looks essentially random day to day with no directional trend, the collector is very likely storing a raw daily rate instead of a rolling/cumulative figure.

### Pitfall 2: The scorer's `'stars'` literal silently producing zero-eligible entities, not a visible failure
**What goes wrong:** `run_manifest` will show `status='success'` with a healthy `item_count` for `collect:hn`/`collect:npm`/`collect:pypi`/`collect:changelog` (collection and snapshot-writing both succeed). `scores` rows will also be written (one per entity, per `rescore_all`'s "always write a row, eligible or not" contract) — they will just always be `eligible=0, wilson_lower_bound=0.0`. Nothing in `run_manifest`, logs, or the health strip surfaces this as a problem, because from every other layer's point of view, everything ran cleanly.
**Why it happens:** `compute_window_gain`'s SQL literal `metric_name = 'stars'` fails closed (empty result set → `WindowGain(0,0,0)`), not loudly.
**How to avoid:** Implement the `PRIMARY_METRIC`/parameterized-`compute_window_gain` fix from Architecture Pattern 2 as part of this phase's plan, not as a follow-up. Add a regression test asserting a non-GitHub entity with real snapshot history produces a non-zero `wilson_lower_bound` after `rescore_all` — mirroring the existing GitHub scoring tests in `tests/test_scoring.py`.
**Warning signs:** New sources appear in `run_manifest` as `success` with real `item_count`, but never appear on the dashboard even after several days of collection, and `query_partial_history_count` doesn't explain it either (their `window_days` in `scores` would show as growing normally, just always `eligible=0`).

### Pitfall 3: GitHub's Search-API-specific rate-limit assumptions leaking into new collectors
**What goes wrong:** `github.py`'s retry/backoff (`is_retryable`) is tuned to GitHub's specific 403-with-`x-ratelimit-remaining:0` signal. Algolia HN, npm registry, and pypistats do not use that convention — Algolia is generally generous (~10k req/hr per IP, community-documented, not an official Algolia SLA) but returns plain `429` on throttling; `api.npmjs.org` and `pypistats.org` similarly use standard `429`/`5xx`.
**Why it happens:** Copy-pasting `github.py`'s `_RETRY_KWARGS`/`is_retryable` verbatim without adjusting the retry predicate for the new APIs' actual throttling signals.
**How to avoid:** Write a small, source-appropriate `is_retryable` (retry on `429` and `5xx`; treat `404`/other `4xx` as permanent) for the new collectors' HTTP calls, rather than importing GitHub's exact predicate.
**Warning signs:** A collector silently drops results whenever the upstream returns 429 (not retried, not logged as an error) or, worse, retries a permanent 4xx in a tight loop.

## Code Examples

### Hacker News — Algolia Search API (verified live, 2026-08-19)
```
GET https://hn.algolia.com/api/v1/search_by_date
    ?query=<keyword>
    &tags=story
    &numericFilters=created_at_i>{unix_ts_lookback_cutoff}
    &hitsPerPage=50
```
Confirmed live response shape (fetched directly this session):
```json
{
  "hits": [{
    "objectID": "12345678",
    "title": "Show HN: ...",
    "url": "https://example.com/...",
    "author": "someuser",
    "points": 142,
    "num_comments": 37,
    "created_at": "2026-08-18T10:00:00.000Z",
    "created_at_i": 1755500000,
    "story_id": null,
    "story_text": null,
    "_tags": ["story", "author_someuser", "story_12345678"]
  }]
}
```
- No historical backfill possible — Algolia only indexes what was posted (confirms CONTEXT.md's expectation of first-week sparseness, same shape as GitHub's D-08a).
- Rate limit: community-documented ~10,000 requests/hour/IP (no official Algolia SLA found for the free HN index — treat as `[ASSUMED]`, see Assumptions Log).
- `story_text` is populated for Ask HN/Show HN self-posts (no external `url`) — fall back to `https://news.ycombinator.com/item?id={objectID}` when `url` is null, exactly like a self-post has no homepage.

### npm downloads (verified via official npm/registry docs, GitHub-hosted)
```
GET https://api.npmjs.org/downloads/point/last-week/{package}
```
```json
{ "downloads": 31623, "start": "2026-08-12", "end": "2026-08-18", "package": "some-pkg" }
```
- Scoped packages (`@org/pkg`) must URL-encode the slash as `%2F` for single-package queries.
- Bulk (comma-separated) queries capped at 128 packages, but bulk mode does not support scoped packages — use per-package requests if any tracked package is scoped.
- Data available back to 2015-01-10; standard queries capped at 18 months lookback (irrelevant here — only `last-week` is needed daily).

### PyPI downloads via `pypistats` API (verified via official pypistats.org/api)
```
GET https://pypistats.org/api/packages/{package}/recent
```
```json
{ "data": { "last_day": 120, "last_week": 3400, "last_month": 14000 }, "package": "some-pkg", "type": "recent_downloads" }
```
- Data updates once daily — no benefit to polling more than once/day (matches the project's daily-run cadence anyway).
- Excludes known mirror traffic by default (`mirrors=false` implicit) — appropriate default, no action needed.
- IP-based rate limiting is documented as applying "application-wide" — no published numeric ceiling found; poll at most once/day per tracked package (matches project cadence, effectively self-limiting).

### Changelogs via `feedparser` — verified reachable feed URLs (curl'd live, 2026-08-19)
| Feed | URL | HTTP status | Notes |
|------|-----|-------------|-------|
| OpenAI News | `https://openai.com/news/rss.xml` | 200 (`text/xml`) | Official first-party feed |
| GitHub Changelog | `https://github.blog/changelog/feed/` | 200 (`application/rss+xml`) | Official first-party feed |
| Hugging Face Blog | `https://huggingface.co/blog/feed.xml` | 200 (`application/rss+xml`) | Official first-party feed |
| Aider (GitHub Releases) | `https://github.com/Aider-AI/aider/releases.atom` | 200 (`application/atom+xml`) | GitHub-native per-repo releases feed — no auth needed, works for any public repo |
| Ollama (GitHub Releases) | `https://github.com/ollama/ollama/releases.atom` | 200 | Same pattern — **Ollama's own blog has no RSS feed** (confirmed via GitHub issues #1669/#3558, feature requested but not shipped) |
| LangGraph (GitHub Releases) | `https://github.com/langchain-ai/langgraph/releases.atom` | 200 | Same pattern |
| llama.cpp (GitHub Releases) | `https://github.com/ggml-org/llama.cpp/releases.atom` | 200 | Same pattern |
| Claude Code (GitHub Releases) | `https://github.com/anthropics/claude-code/releases.atom` | 200 | **Anthropic has no official RSS feed** (confirmed — only unofficial third-party mirrors exist, e.g. `tim-hilde.github.io/anthropic-rss`); GitHub Releases Atom is the reliable first-party substitute for tools that ship on GitHub |
| ~~`anthropic.com/rss.xml`~~ | — | 404 | Does not exist — do not seed this URL |
| ~~`ollama.com/blog/rss`~~ | — | 404 | Does not exist — do not seed this URL |

```python
import feedparser
from datetime import date, timedelta, datetime, UTC

def count_entries_in_window(feed_url: str, lookback_days: int) -> tuple[int, list[dict]]:
    parsed = feedparser.parse(feed_url)  # parsed.bozo is True on malformed feeds — log, don't raise
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    in_window = []
    for entry in parsed.entries:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published is None:
            continue
        entry_dt = datetime(*published[:6], tzinfo=UTC)
        if entry_dt >= cutoff:
            in_window.append(entry)
    return len(in_window), in_window
```
`feedparser` normalizes both RSS 2.0 (`published`) and Atom (`updated`) into the same `*_parsed` `time.struct_time` fields — no separate RSS-vs-Atom branching needed in the collector.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| (N/A — this is greenfield within the project) | — | — | — |

No deprecated/outdated APIs found for HN Algolia, npm downloads, or pypistats — all three are stable, long-lived public APIs with no announced sunset.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | Algolia HN Search API rate limit is ~10,000 requests/hour/IP | HN code example | If actually lower, the collector could get throttled mid-run; low impact since the project only needs a handful of requests/day (one per tracked keyword) |
| A2 | `feedparser` 6.0.14's XML parsing has no exploitable XXE/entity-expansion issue when pointed at curated (not user-supplied) feed URLs | Package Legitimacy Audit / Security Domain | Feed URLs are entirely curated in `tracked.toml` (D3-4), never user input, so blast radius of any parser vulnerability is limited to trusted, hand-picked URLs — but this was not independently verified against feedparser's current security advisories this session |
| A3 | Treating npm/PyPI's `last-week` rolling total (not the raw daily count) as the daily `metric_value` produces a directionally sound week-over-week momentum signal when run through the existing last-minus-first `compute_window_gain` math | Common Pitfall 1 | If wrong, downloads-based ranking could be noisier than intended; low severity since D-13 already defers real calibration, and the floor/eligibility gate would just need retuning, not an architecture change |
| A4 | HN points, once a story ages off the front page, are stable enough that GitHub's last-minus-first window-gain math (built for a monotonic counter) still produces a sane "points gained" figure for HN entities | HN section | If wrong (e.g., points genuinely fluctuate non-monotonically day to day for an aged story), gain could occasionally read as a small negative/zero value for an entity that's actually still relevant — low severity, matches the project's stated tolerance for first-week sparseness |

## Open Questions

1. **What is the exact `window_gain_floor` for HN points / npm+PyPI downloads / changelog releases?**
   - What we know: GitHub's floor is `25` stars gained in 7 days (config default). These are wildly different scales (a popular npm package can gain tens of thousands of downloads/week; an HN story rarely exceeds a few hundred points).
   - What's unclear: A single global `window_gain_floor` tunable will not work across all four sources.
   - Recommendation: Either add a per-source floor to `Tunables` (e.g. `window_gain_floor_hn`, `window_gain_floor_downloads`, `window_gain_floor_releases`, defaulting conservatively) or explicitly accept in this phase that non-GitHub sources will need floor recalibration in a follow-up once real data exists (matches D-13's "build the seam, calibrate later" philosophy) — planner's call, but should be a named decision, not an oversight.

2. **Should `queries.py`'s `stars_total` subquery be generalized to each entity's own primary metric, or left GitHub-only with `—` for other sources?**
   - What we know: Leaving it as-is is not a crash — the template already renders `NULL` as `—`.
   - What's unclear: Whether showing `—` in a "Total" column for every non-GitHub row is an acceptable v1 UX tradeoff, or whether it undermines the dashboard's usefulness for the new sources.
   - Recommendation: Ship with the label generalization (`table.html` header text) as a required fix (Finding 2), but treat generalizing the `stars_total` subquery's metric-name binding as a nice-to-have the planner can descope if time-constrained — it degrades gracefully either way.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|----------|-----------|
| `hn.algolia.com` (Algolia HN Search) | COLL-03 | Reached live this session, 200 OK | n/a (public API) | none needed — no auth, no token |
| `api.npmjs.org` | COLL-04 (npm) | Documented, standard public endpoint (not directly curl'd this session, but confirmed via official npm/registry GitHub docs) | n/a | none needed |
| `pypistats.org/api` | COLL-04 (PyPI) | Documented, standard public endpoint (confirmed via official pypistats.org/api page) | n/a | none needed |
| GitHub `releases.atom` feeds | COLL-05 (changelog) | Reached live this session for 5 repos, all 200 OK | n/a | already-tracked GitHub repos' own release feeds are a reliable default source list |
| `openai.com/news/rss.xml`, `github.blog/changelog/feed/`, `huggingface.co/blog/feed.xml` | COLL-05 (changelog) | Reached live this session, all 200 OK | n/a | none needed |
| `anthropic.com/rss.xml`, `ollama.com/blog/rss` | COLL-05 (changelog) | **Confirmed 404 — do not use** | n/a | use `github.com/anthropics/claude-code/releases.atom` and `github.com/ollama/ollama/releases.atom` instead |
| `feedparser` (pip package) | COLL-05 (changelog) | Available on PyPI, `6.0.14` current | 6.0.14 | none needed |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Anthropic and Ollama official blog RSS — both have a working fallback (GitHub Releases Atom), listed above.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` ≥8, with `pytest-postgresql` for the ephemeral-cluster `db` fixture |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| Quick run command | `pytest -q tests/test_collect_hn.py tests/test_collect_packages.py tests/test_collect_changelog.py` |
| Full suite command | `pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| COLL-03 | HN collector fetches + normalizes stories into `CollectedItem` with `metrics={"points": N}` | unit (fixture-backed, `httpx.MockTransport`) | `pytest tests/test_collect_hn.py -x` | ❌ Wave 0 |
| COLL-04 | npm/PyPI collectors fetch + normalize download counts into `metrics={"downloads": N}` | unit (fixture-backed) | `pytest tests/test_collect_packages.py -x` | ❌ Wave 0 |
| COLL-05 | Changelog collector counts feed entries in the trailing window into `metrics={"releases": N}` | unit (fixture-backed, local sample XML/Atom fixture — no live network) | `pytest tests/test_collect_changelog.py -x` | ❌ Wave 0 |
| (regression) `compute_window_gain` parameterized correctly per source | A non-GitHub entity with real snapshot history scores non-zero after `rescore_all` | unit/integration (uses `db` fixture) | `pytest tests/test_scoring.py -k multi_source -x` | ❌ Wave 0 (extend existing `tests/test_scoring.py`) |
| (regression) Registry grows to 5 entries, all satisfy `Collector` protocol | Structural | `pytest tests/test_collect_github.py::test_collectors_registry_has_exactly_one_entry_satisfying_protocol` **must be updated** — the existing assertion `len(COLLECTORS) == 1` will need to become `== 5` (or the test renamed/moved) | ⚠️ existing test needs editing, not just a new one |

### Sampling Rate
- **Per task commit:** the relevant new-collector test file, plus `tests/test_scoring.py` if `score.py` was touched
- **Per wave merge:** `pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_collect_hn.py` — covers COLL-03
- [ ] `tests/test_collect_packages.py` — covers COLL-04
- [ ] `tests/test_collect_changelog.py` — covers COLL-05
- [ ] `tests/fixtures/hn/`, `tests/fixtures/packages/`, `tests/fixtures/changelog/` — recorded sample responses, mirroring `tests/fixtures/github/`
- [ ] Extend `tests/test_scoring.py` with a multi-source `compute_window_gain`/`rescore_all` case
- [ ] Update `tests/test_collect_github.py::test_collectors_registry_has_exactly_one_entry_satisfying_protocol` (existing test, will break once `COLLECTORS` grows — must be edited as part of this phase, not left red)

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V5 Input Validation | yes | `CollectedItem` (pydantic, `extra="forbid"`) already validates every collector's normalized output at the boundary — new collectors inherit this for free, no new work needed |
| V12 Files and Resources (XML parsing) | yes | `feedparser` parses externally-hosted XML/Atom content — verify no XXE/entity-expansion exposure (see Assumption A2); mitigated in depth by feed URLs being curated-only (`tracked.toml`, D3-4), never accepting a user-supplied URL at runtime |
| V13 API and Web Service | yes | All three new outbound integrations (Algolia, npm, pypistats) are unauthenticated public GET APIs — no secrets to leak, no `http.py`-style token-confinement concern for these three (only the GitHub client carries a secret) |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| SSRF via feed URL | Tampering/Information Disclosure | Not applicable in v1 — feed URLs are curated by the project owner in `tracked.toml`, never accepted from a request/API param; if a future phase ever exposes "add a changelog feed" as a user-facing action, this control must be revisited |
| XXE / billion-laughs via malicious feed content | Denial of Service / Information Disclosure | `feedparser` is generally considered safe-by-default against classic XXE (does not resolve external entities by default in modern versions) — not independently re-verified against feedparser's current CVE list this session (Assumption A2); low practical risk here since all feed sources are hand-picked, reputable vendor/GitHub domains, not arbitrary user-submitted URLs |
| Rate-limit exhaustion / unintentional DoS against a public third-party API | — | Each new collector should implement its own `is_retryable` tuned to the target API's actual throttling signal (429/5xx), matching Common Pitfall 3 above — never retry indefinitely against a public service the project doesn't control |

## Sources

### Primary (HIGH confidence)
- Direct codebase reads: `techtrend/collectors/base.py`, `github.py`, `registry.py`, `http.py`; `techtrend/pipeline/normalize.py`, `score.py`, `snapshot.py`; `techtrend/db/schema.sql`; `techtrend/pipeline/orchestrator.py`, `identity.py`; `techtrend/server/queries.py`; `techtrend/web/templates/partials/table.html`; `config/tracked.toml`; `techtrend/config.py`; `tests/test_collect_github.py`, `tests/conftest.py` — all read this session, line numbers cited inline above
- Live-fetched HN Algolia search response (`hn.algolia.com/api/v1/search`) — actual JSON structure confirmed, not from documentation alone
- Live `curl` reachability checks (2026-08-19) for `openai.com/news/rss.xml`, `github.blog/changelog/feed/`, `huggingface.co/blog/feed.xml`, and 5 GitHub `releases.atom` URLs — all `200`
- Live `curl` checks confirming `anthropic.com/rss.xml` and `ollama.com/blog/rss` return `404`
- `pip index versions feedparser` — confirmed `6.0.14` current, full version history back to `4.1`

### Secondary (MEDIUM confidence)
- `github.com/npm/registry/blob/main/docs/download-counts.md` (official npm registry docs, WebFetch-summarized) — point/range endpoint shapes, bulk-query limits, scoped-package caveat
- `pypistats.org/api/` (official pypistats docs, WebFetch-summarized) — recent/overall endpoint shapes, mirror-exclusion default, daily update cadence
- WebSearch-confirmed: Anthropic has no official RSS feed (community GitHub issue/mirror threads); Ollama blog has no RSS feed (GitHub issues #1669, #3558)

### Tertiary (LOW confidence)
- Algolia HN Search API ~10,000 req/hr/IP rate limit — WebSearch-sourced, no official Algolia SLA page found confirming this number for the free HN index (Assumption A1)
- `feedparser` XXE safety posture — general training knowledge, not independently re-verified against current CVE databases this session (Assumption A2)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies beyond `feedparser`, version verified directly against PyPI
- Architecture (scorer gap): HIGH — read directly from `score.py`'s source, not inferred; this is the single most load-bearing finding in this document
- External API shapes: MEDIUM — npm/pypistats confirmed via official docs pages (not live-curled JSON this session); HN confirmed via a live request this session
- Pitfalls: MEDIUM — Pitfall 1/2 derived from direct code reading (HIGH); Pitfall 3 is reasonable inference from the codebase's existing retry pattern (MEDIUM)

**Research date:** 2026-08-19
**Valid until:** 30 days for the codebase-derived findings (Findings 1/2, stable until the code changes); external API shapes should be re-verified if this research is reused after ~60-90 days (all three APIs are stable/long-lived, low churn risk)
