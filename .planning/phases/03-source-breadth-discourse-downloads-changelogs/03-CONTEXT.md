# Phase 3: Source Breadth — Discourse, Downloads & Changelogs — Context

**Gathered:** 2026-08-19
**Status:** Ready for planning (research recommended first)

<domain>
## Task Boundary

Add three new sources — **Hacker News** (discourse), **npm/PyPI** (download velocity), and **vendor changelogs** (releases) — to the existing pipeline, each flowing through the proven collector-plugin seam with **no changes to the scorer, gate, enricher, or ranking step** (COLL success-criterion 3). Every source is "one collector module + one `registry.py` line + one `normalize.py` converter."

Reusable seam already in place (scouted 2026-08-19):
- `techtrend/collectors/base.py` — `Collector` Protocol (`fetch(since) -> list[dict]`, `normalize(raw) -> CollectedItem`) and the strict `CollectedItem` contract. `metrics: dict[str,int]` is a flat source-agnostic bag (e.g. `{"stars": N}`, `{"points": N}`, `{"downloads": N}`, `{"releases": N}`), so the snapshot writer stays source-blind.
- `techtrend/collectors/registry.py` — `COLLECTORS` list the orchestrator iterates; the only file that names concrete sources.
- `techtrend/pipeline/normalize.py` — `momentum_for_source(source, gain, total)` dispatch + `_CONVERTERS`. GitHub is the identity mapping. D-13: **build the converter seam, calibrate later** — do NOT attempt real cross-source calibration against points/downloads that have never been observed.
</domain>

<decisions>
## Implementation Decisions (LOCKED — do not revisit)

### D3-1. Scope: all three sources
Build Hacker News, npm/PyPI, and vendor changelogs in this phase. Three collector modules (npm + PyPI may share one module or be two — planner's call), each registered + given a `normalize.py` converter.

### D3-2. Cross-source dedup: DEFERRED (separate rows for v1)
Each source produces its **own** entity — GitHub `aider` and an Aider changelog feed are separate dashboard rows for now. **COLL success-criterion 2 (same release on GitHub + changelog resolves to one entity) is explicitly descoped to a follow-up** — cross-source identity resolution is hard and low-frequency; ship the sources first. Record this descope honestly in REQUIREMENTS/ROADMAP (mirror the SQLite→Postgres supersession style), don't silently drop it.

### D3-3. Changelog ranking: releases-in-window as momentum
A changelog "release" is an event, not a cumulative count. Count the **releases within the trailing window** and feed that through a `normalize.py` converter as the `(gain, total)` momentum pair — so changelogs rank through the **existing** velocity model with **no scorer change**. Metric key: `{"releases": <count>}`.

### D3-4. Source lists: curated in config/tracked.toml
Which HN keywords, which npm/PyPI packages, and which changelog feed URLs are tracked is **hand-curated in `config/tracked.toml`** (new sections, mirroring the existing `[seed]`/`[discovery]` pattern), validated through `techtrend/config.py`. NOT auto-derived from tracked GitHub repos.

### D3-5. SC3 revision — minimal, DOCUMENTED scorer + dashboard + client touches (added post-research 2026-08-19)
Research (`03-RESEARCH.md`, commit `c8e7807`) proved the codebase is NOT as source-agnostic as documented. COLL success-criterion 3 ("adding a source requires NO change to scorer/gate/enricher/dashboard") is **infeasible as literally stated** and is hereby **revised** — recorded honestly (SQLite→Postgres precedent), not silently. The following minimal touches are LOCKED as in-scope, named deviations:
- **Scorer (unavoidable):** `score.py::compute_window_gain` hardcodes `WHERE metric_name = 'stars'` (score.py:103). Parameterize the momentum metric name — resolved per source via a `PRIMARY_METRIC` lookup living in `normalize.py` (e.g. github→stars, hackernews→points, npm/pypi→downloads, changelog→releases). Without this, every non-GitHub entity scores `eligible=0` forever with no visible failure. Keep the change mechanical; do NOT touch the Wilson math or the gate/enricher.
- **Dashboard (user chose "Generalize the labels"):** `queries.py` `SORT_KEYS`/`stars_total` and `table.html` hardcode `'stars'` / "Stars"/"Stars gained". Generalize to source-agnostic wording (e.g. "Momentum"/"Gained" or per-source metric) so multi-source rows read correctly. Small template + query touch, documented.
- **HTTP client:** `http.py::build_client()` hard-requires `GITHUB_TOKEN`; the three new sources are unauthenticated public APIs. Add a separate/parameterized unauthenticated client — do NOT loosen the GitHub client's token requirement.

Everything else in the ranking gate and enricher stays untouched. These three touches are the whole deviation surface — the planner must not expand it.

### Claude's Discretion (decide during research/planning)
- **HN collector:** Algolia HN Search API (`https://hn.algolia.com/api/v1/search`), query by the AI/LLM keywords (reuse/extend `[discovery].keywords`). Primary momentum signal = story **points** (comments optional/secondary). No historical backfill exists → HN will be sparse for the first ~week exactly like GitHub's D-08a honesty; that is expected, not a bug.
- **npm/PyPI collectors:** npm downloads via `https://api.npmjs.org/downloads/`, PyPI via the pypistats API. Metric = `{"downloads": N}`; momentum = downloads gained over the window.
- **Changelogs:** `feedparser` over curated RSS/Atom feed URLs; each feed entry within the window counts as a release. Entity `full_name` from the feed/config label.
- npm/PyPI as one "packages" collector vs. two separate — planner's call.
</decisions>

<specifics>
## Specific Ideas / Expected Deliverables

- New dependency: **`feedparser`** (~6.0.x, already named in the CLAUDE.md supporting-libs table) for changelog RSS/Atom — add to `pyproject.toml`.
- New `config/tracked.toml` sections (curated) for: HN keywords (or reuse discovery), npm/PyPI package names, changelog feed URLs — each with a `techtrend/config.py` Pydantic model.
- Three collectors implementing `Collector`, each added to `COLLECTORS` (one line) and `_CONVERTERS` (one converter). Per-source `metrics` keys: `points` (HN), `downloads` (npm/PyPI), `releases` (changelog).
- Follow the existing GitHub collector's test pattern (fixture-backed, no live network in tests — `httpx.MockTransport` / bundled fixtures), mirroring `tests/test_collect_github.py`.
</specifics>

<deferred>
## Deferred / Out of Scope

- **Cross-source identity resolution / dedup (COLL SC2)** — deferred per D3-2; separate rows per source for v1.
- **Real cross-source momentum calibration** — per D-13, converters stay near-identity until there is observed points/downloads/releases data to calibrate against.
</deferred>

<canonical_refs>
## Canonical References & Open Integration Questions for Research/Planning

- `techtrend/collectors/base.py`, `registry.py`, `github.py` — the seam + the one worked example to mirror.
- `techtrend/pipeline/normalize.py` — where each source's `(gain,total)` converter goes.
- `techtrend/pipeline/score.py::compute_window_gain` — **RESEARCH MUST VERIFY** how the scorer selects an entity's momentum metric from `snapshots` per source (GitHub uses stars). Adding points/downloads/releases must slot into this without a scorer edit — confirm the snapshot/metric selection is already source-parameterized or identify the minimal seam.
- Dashboard tension (**flag for planner**): the dashboard currently shows star-specific columns ("Stars", "Stars gained"). Multi-source rows (points/downloads/releases) have no "stars." SC3 says *no dashboard code changes to add a source* — reconcile by confirming the existing columns render source-agnostically, or note a small, honest label-generalization deviation if required. Do not silently ship GitHub-only column labels over multi-source data.
- CLAUDE.md — supporting-libs table (`feedparser`, `httpx`, `pydantic`), and the honest-supersession precedent for recording the COLL-SC2 descope.
</canonical_refs>
