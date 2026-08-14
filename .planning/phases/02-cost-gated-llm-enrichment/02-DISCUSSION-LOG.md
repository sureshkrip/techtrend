# Phase 2: Cost-Gated LLM Enrichment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-13
**Phase:** 2-cost-gated-llm-enrichment
**Areas discussed:** Section ambiguity handling, Cost-cap overflow behavior, Batch vs synchronous LLM, Section-browsing UX, Grounding source, Cache/re-enrichment

---

## Section ambiguity handling

| Option | Description | Selected |
|--------|-------------|----------|
| Force-pick + confidence flag | Assign best of seven, store confidence, flag low-confidence filings | ✓ |
| 'Unsorted' review bucket | 8th catch-all below a threshold — extends the fixed taxonomy | |
| Force-pick, no signal | Always one of seven, confidence not surfaced | |

**User's choice:** Force-pick + confidence flag → CONTEXT D-02
**Notes:** Keeps the taxonomy fixed at seven; the flag is the safety valve.

| Option | Description | Selected |
|--------|-------------|----------|
| Single structured call | One Haiku call returns summary + section + confidence | ✓ |
| Two separate calls | Summarize then classify — ~2x cost, two failure points | |

**User's choice:** Single structured call → CONTEXT D-01

---

## Cost-cap overflow behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Top-velocity first, defer rest | Overflow stays ranked-pending, first in line next run | ✓ |
| Top-velocity first, drop rest | Overflow never enriched unless it re-qualifies | |
| Newest-discovered first | Novelty over momentum | |

**User's choice:** Top-velocity first, defer rest → CONTEXT D-05

| Option | Description | Selected |
|--------|-------------|----------|
| Ranked row, no summary, 'pending' hint | Visible + ranked, quiet 'summary pending' | ✓ |
| Ranked row, blank summary cell | Visible but no explanation | |
| Hidden until enriched | Loses visibility — violates ENR-06 spirit | |

**User's choice:** Ranked row + 'pending' hint → CONTEXT D-10

---

## Batch vs synchronous LLM

| Option | Description | Selected |
|--------|-------------|----------|
| Synchronous within the daily run | Simple, immediate; cap keeps volume tiny | ✓ |
| Batch API | ~50% cheaper but async submit→poll→ingest | |

**User's choice:** Synchronous → CONTEXT D-06 (batch deferred, not rejected)

| Option | Description | Selected |
|--------|-------------|----------|
| Claude Haiku 4.5 | CLAUDE.md pick; cheapest that clears the bar | ✓ |
| Claude Sonnet 5 | Higher accuracy, materially higher cost | |
| You decide | Leave to researcher spot-check | |

**User's choice:** Haiku 4.5 → CONTEXT D-03 (Sonnet upgrade deferred)

---

## Section-browsing UX

| Option | Description | Selected |
|--------|-------------|----------|
| Left sidebar, single-section filter, 'All' default + counts | htmx GET → table partial | ✓ |
| Top tabs | Worse scan density | |
| Multi-select filter | More UI state | |

**User's choice:** Left sidebar → CONTEXT D-11

| Option | Description | Selected |
|--------|-------------|----------|
| Same dense table everywhere | Filter narrows rows; one layout | ✓ |
| Distinct per-section layout | More work, inconsistent | |

**User's choice:** Same table → CONTEXT D-12

| Option | Description | Selected |
|--------|-------------|----------|
| Under 'All' only, until enriched | Section = has a real filing | ✓ |
| An 'Unsorted' nav entry | Adds an 8th nav bucket | |

**User's choice:** Under 'All' only → CONTEXT D-13

---

## Grounding source

| Option | Description | Selected |
|--------|-------------|----------|
| README intro + repo description | Top section before first deep heading, capped | ✓ |
| Full README + description | Max grounding, more tokens/noise | |
| Description only | Cheapest, often too thin | |

**User's choice:** README intro + description → CONTEXT D-07

| Option | Description | Selected |
|--------|-------------|----------|
| No summary + honest marker, stays ranked | Skip the call, never fabricate | ✓ |
| Summarize from description alone | Risks weak/misleading line | |

**User's choice:** No summary + honest marker → CONTEXT D-08

---

## Cache / re-enrichment

| Option | Description | Selected |
|--------|-------------|----------|
| Hash grounding text; change re-summarizes AND re-files | Pivoted tool can move sections | ✓ |
| Hash grounding text; re-summarize only, keep section | Would stay mis-filed after a pivot | |
| Hash a version tag / commit SHA | Misses README edits, over-triggers on commits | |

**User's choice:** Hash grounding text, re-summarize + re-file → CONTEXT D-09

---

## Claude's Discretion

- Exact numeric defaults for per-run enrichment cap and grounding char cap (config Tunables).
- Precise `anthropic` SDK surface (structured-output schema, prompt wording); whether the seven section definitions live in config (leaning yes) vs. embedded in the prompt.
- Content-hash algorithm + grounding-text normalization.
- Confidence representation and the low-confidence-flag threshold.
- Whether release events (COLL-01) participate in grounding.

## Deferred Ideas

- Anthropic Batch API — fast-follow if enriched volume grows.
- Grounding on non-GitHub source text — Phase 3 collectors plug into the same seam.
- 'Unsorted' nav bucket / 8th section — rejected; taxonomy stays fixed at seven.
- Sonnet 5 for classification — targeted upgrade only if Haiku accuracy proves weak.
