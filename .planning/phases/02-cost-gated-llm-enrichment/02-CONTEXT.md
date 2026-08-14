# Phase 2: Cost-Gated LLM Enrichment - Context

**Gathered:** 2026-08-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Add the first LLM stage to the pipeline: items that clear Phase 1's ranking gate (`scores.eligible = 1` at the current score version) receive a grounded two-line "what this is / why it matters" summary and are filed into exactly one of the seven fixed sections — within a hard per-run LLM budget — and the read-only dashboard gains left-nav section browsing. Enrichment problems must never remove an already-ranked item from view.

**In scope:** DATA-04 (content-hash enrichment cache), ENR-01 (only ranking-threshold survivors reach the LLM), ENR-02 (hard per-run cap), ENR-03 (two-line summary), ENR-04 (one-of-seven section), ENR-05 (grounded on freshly fetched source text), ENR-06 (failure never loses ranked data), DASH-02 (browse/filter by section).

**Explicitly NOT in this phase:**
- No new collectors — Hacker News, npm/PyPI, RSS are Phase 3 (COLL-03/04/05). Enrichment grounding this phase is GitHub-only (README + description); the grounding seam is built so Phase 3 sources plug in later.
- No scheduler wiring — Phase 4 (SCHED-01/02).
- No Batch API — synchronous enrichment for MVP (see D-05); batch deferred, not rejected.
- No changes to the Phase 1 ranking/scoring math — enrichment reads the existing eligible seam, it does not re-rank.
</domain>

<decisions>
## Implementation Decisions

### Section Assignment & Summary (ENR-03, ENR-04)

- **D-01:** One **structured LLM call per item** returns `{summary_line_1, summary_line_2, section, confidence}` via the `anthropic` SDK's structured-outputs support. Atomic, cheapest, one cache entry per item. Not two separate summarize/classify calls.
- **D-02:** **Force-pick exactly one of the seven fixed sections** (ENR-04) — the taxonomy stays fixed at seven, no 8th "Unsorted" bucket. The model also returns a **confidence**; low-confidence filings carry a **subtle visual flag** in the dashboard so mis-files are spottable at a glance. Confidence representation/threshold is Claude's discretion (see below).
- **D-03:** **Model = Claude Haiku 4.5** (the CLAUDE.md stack pick — cheapest model that clears the bar for a 2-line summary + 1-of-7 label). Upgrade only this call to Sonnet 5 later if borderline classification proves weak; the task is deliberately Haiku-shaped.

### Cost Gate & Overflow (ENR-01, ENR-02)

- **D-04:** The enrichment gate reads the **existing Phase 1 ranking seam** — `scores.eligible = 1` at `CURRENT_SCORE_VERSION` (see `techtrend/server/queries.py::query_ranked`). Items clearing the ranking threshold are the enrichment candidates. The **hard per-run cap** is a config `Tunable`, independent of the ranking threshold (ENR-02).
- **D-05:** On overflow (more eligible items than the cap): **enrich highest-velocity first up to the cap; the overflow stays ranked-but-unenriched and is first in line on the next run** while still eligible. Nothing high-signal is permanently dropped. (Newest-first and permanent-drop were both rejected — velocity-first matches the core value.)
- **D-06:** **Synchronous** enrichment stage inside the daily run — no Batch API for MVP. The per-run cap keeps volume to a handful of cheap Haiku calls, so the ~50% Batch savings is negligible in absolute terms and not worth the submit→poll→ingest orchestration + up-to-hours latency. Revisit batch as a fast-follow if daily enriched volume ever grows large.

### Grounding & Anti-Fabrication (ENR-05, SC3)

- **D-07:** Ground each GitHub summary on the **repo description + README intro** — the README's top section (before the first deep heading, capped to ~N chars; N is a config `Tunable`). Not the full README (token/noise cost), not description-only (too thin for a real "why it matters" line).
- **D-08:** If the grounding text **can't be fetched or is effectively empty**, **skip the LLM call entirely** and show the ranked row with an honest **"no summary — source unavailable"** marker. Never fabricate from the model's parametric knowledge. (Mirrors Phase 1's honesty instinct.)

### Cache & Re-enrichment (DATA-04, SC4)

- **D-09:** Enrichment cache is keyed on **(entity, content_hash)** where `content_hash` = a hash of the **exact fetched grounding text sent to the LLM**. Unchanged text → the LLM is **never re-called** (SC4). Changed grounding text (e.g. a rewritten README) → the next run produces **both a fresh summary and a fresh section** — a tool that genuinely pivoted can move sections. (Re-summarize-but-pin-section and hash-a-commit-SHA were rejected.)

### Failure Isolation (ENR-06)

- **D-10:** Any enrichment failure — LLM error, fetch failure, or cap overflow — **never removes the item**. It stays ranked with a quiet **"summary pending"** (capped/queued) or **"source unavailable"** (fetch failed) marker in the summary cell. Enrichment problems never cost visibility into already-ranked data — the direct analog of Phase 1's "backfill failure never blocks live collection" (D-08).

### Dashboard Section Browsing (DASH-02)

- **D-11:** A **persistent left sidebar** lists the seven sections with a **per-section count**; clicking one filters the ranked table to that section via an **htmx GET returning the table partial** — the same interaction pattern as Phase 1's sort (D-14). **"All" is the default** full ranked list. Top-tabs and multi-select were rejected (worse scan density / more UI state).
- **D-12:** **Same dense table, sort controls, and health strip in every view** — the section filter only narrows the rows. No second layout to build or maintain.
- **D-13:** **Unenriched items (no section yet) appear under "All" only**; they gain a section filter once enriched. The seven sections mean "has a real filing." Low-confidence filings (D-02) still file into their best section but carry the visual flag.

### Schema & Structure

- **D-14:** Add the **`enrichments` table** (anticipated in ARCHITECTURE.md's schema) via a forward migration alongside the existing `entities`/`snapshots`/`scores`/`run_manifest` tables. The dashboard's `query_ranked` **LEFT JOINs** enrichments so eligible-but-unenriched items still render (D-10/D-13). Enrichment is a new **pipeline stage** in the orchestrator, run after scoring, recording its own `run_manifest` health row.
- **D-15:** All enrichment knobs — per-run cap, grounding char cap, model id, confidence threshold — live in the config **`Tunables`** Pydantic model, **not code constants**, consistent with Phase 1.

### Claude's Discretion

The user consistently took the recommended option; these were the recommendations, so treat them as decided. Genuinely open for research/planner:

- Exact numeric defaults for the enrichment cap and grounding char cap (shape decided above; config, not constant).
- The precise `anthropic` SDK surface — Messages API structured-output schema shape, prompt wording, how the seven section **definitions** are supplied to the model. **Lean toward keeping the section definitions in config** (a non-secret config file) so the taxonomy is editable without a code change, consistent with Phase 1's config-driven seed/allowlist lists.
- Content-hash algorithm (e.g. sha256) and any normalization of the grounding text (whitespace/badge stripping) before hashing.
- How `confidence` is represented and the threshold that trips the low-confidence visual flag.
- Whether release events (COLL-01) participate in grounding or only stars — likely stars/README for MVP.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### LLM integration (load-bearing for this phase)
- `.claude/CLAUDE.md` — **Locked stack**: `anthropic` SDK, **Claude Haiku 4.5** for summarize+classify, structured-outputs and Batch API support noted. The model tier and SDK are decided; do not re-litigate. (The "Alternatives Considered" row explains when to upgrade to Sonnet 5.)
- The bundled **`claude-api` skill** (and Anthropic API skill reference) — model ids, pricing, Messages API, **structured outputs** (`output_config.format`), Batch API tradeoffs, token counting. **Read before writing any `anthropic` SDK code** — do not answer model/pricing/structured-output questions from memory.

### Project scope and taxonomy
- `.planning/PROJECT.md` — Core value, the three signal types (releases/traction/discourse), and the **seven-section taxonomy table** (§Context) that ENR-04 files into. The taxonomy test ("exactly one obvious home; revisit if error high") justifies D-02's confidence flag.
- `.planning/REQUIREMENTS.md` — The 8 requirement IDs this phase owns (DATA-04, ENR-01..06, DASH-02) plus v2/Out-of-Scope bounds.
- `.planning/ROADMAP.md` §"Phase 2" — Phase goal and the four success criteria that define done. **UI hint: yes.**

### Architecture and design
- `.planning/research/ARCHITECTURE.md` — **Most important architecture ref.** Defines the `enrichments` table (D-14), the five seams (enrichment is one), the collector plugin interface (grounding-fetch reuse), append-only-snapshot / derived-score separation, and the idempotency mechanisms table (DATA-04/05). §"Build Order" step 5 is this phase.
- `.planning/research/PITFALLS.md` — Silent-failure and grounding/fabrication pitfalls informing D-08/D-10.
- `.planning/research/STACK.md` — Library-level `anthropic`/httpx detail behind the CLAUDE.md summary.
- `.planning/research/FEATURES.md`, `.planning/research/SUMMARY.md` — Supporting context.

### Phase 1 decisions this phase builds on
- `.planning/phases/01-foundation-first-signal-github-scored-and-visible/01-CONTEXT.md` — **D-14** (dense sortable table, built so section filters hang off it without a redesign) and the config-driven `Tunables` pattern D-15 extends.

### Existing code seams (verify at implementation time)
- `techtrend/server/queries.py` — `query_ranked` (the `scores.eligible = 1 AND score_version = CURRENT` seam that IS the enrichment gate D-04 and the dashboard join point D-14) and `query_partial_history_count` (empty-state honesty to preserve).
- `techtrend/db/schema.sql` — current tables; the `enrichments` migration (D-14) lands here.
- `techtrend/config.py` — the `Tunables` Pydantic model that gains the enrichment knobs (D-15).
- `techtrend/pipeline/orchestrator.py` — where the synchronous enrichment stage (D-06/D-14) is inserted after scoring.
- `techtrend/collectors/http.py` / `techtrend/collectors/github.py` — README/description fetch reuse for grounding (D-07).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`query_ranked` (`server/queries.py`)** — already filters to `scores.eligible = 1` at the current score version; this exact query is both the enrichment candidate set (ENR-01) and the dashboard render source. Extend it with a LEFT JOIN to `enrichments`, don't rewrite it.
- **`config.Tunables`** — Pydantic tunables model with the Phase 1 knobs (window_days, floor, caps). Enrichment knobs are added here (D-15).
- **`db/schema.sql` + WAL connection (`db/connection.py`)** — schema + idempotent-upsert conventions to mirror for the `enrichments` table.
- **`pipeline/orchestrator.py`** — the run sequence (collect → snapshot → score); enrichment is a new stage appended after score.
- **htmx sort pattern (Phase 1 D-14, `web/templates` + `server/app.py`)** — GET → HTML table partial; the section sidebar filter (D-11) is the same mechanism with a section query-param.
- **`run_manifest`** — per-stage health rows; the enrichment stage records success/failure here, feeding the D-16 health strip.

### Established Patterns
- **Config-driven, not code-constant** (Phase 1 "Claude's Discretion") — every enrichment knob and the section definitions live in config.
- **Honest degradation over fabrication/hiding** (Phase 1 D-08/D-17, V2 empty-state fix) — D-08/D-10 apply the same instinct to missing summaries.
- **Append-only + derived, keyed by version/hash for free idempotency** (DATA-03/05) — the content-hash cache (D-09) reuses this idea.

### Integration Points
- Enrichment stage reads `scores` (eligible seam), fetches grounding via the GitHub collector's HTTP layer, writes `enrichments`, and records to `run_manifest`.
- Dashboard `app.py`/`queries.py` LEFT JOIN `enrichments`; new sidebar partial + `?section=` param.

</code_context>

<specifics>
## Specific Ideas

- The user explicitly wanted a **left-nav sidebar** filtering by the seven sections — confirmed as D-11 (single-section filter, "All" default, per-section counts).
- Summaries must **visibly reflect fetched source text** — the SC3 anti-fabrication guarantee is treated as a first-class behavior (D-07/D-08), not a soft aspiration.

</specifics>

<deferred>
## Deferred Ideas

- **Anthropic Batch API** — deferred, not rejected (D-06). Revisit as a fast-follow if per-run enriched volume grows enough that the ~50% cost savings outweighs the orchestration/latency cost.
- **Grounding on non-GitHub source text** (HN thread, changelog, package README) — the ENR-05 grounding seam is built GitHub-only this phase; Phase 3 collectors supply their own grounding text through the same seam when they land.
- **"Unsorted" nav bucket / 8th section** — considered and rejected; the taxonomy stays fixed at seven, with the confidence flag (D-02) as the safety valve instead.
- **Sonnet 5 for classification** — deferred as a targeted upgrade of only the enrichment call if Haiku's borderline-section accuracy proves weak in practice (D-03).

</deferred>

---

*Phase: 2-cost-gated-llm-enrichment*
*Context gathered: 2026-08-13*
