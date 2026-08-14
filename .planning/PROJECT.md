# TechTrend

## What This Is

A personal, self-updating intelligence dashboard for the AI coding and LLM ecosystem. It pulls daily from high-signal sources (GitHub star velocity, Hacker News, vendor changelogs, package registries, curated RSS), ranks what it finds by *momentum* rather than absolute popularity, has an LLM summarize and file the survivors into seven fixed sections, and links each tracked tool to its official docs. Built for one user — the owner — as a replacement for scrolling social feeds to stay current.

## Core Value

Open it once a day and know, in five minutes, what is actually gaining traction in AI coding — without scrolling social feeds and without missing the thing that matters.

## Requirements

### Validated

- ✓ Rank by velocity/momentum, not absolute counts — Phase 1 (floor-before-Wilson scorer, unit-verified; a small fast-gaining repo outranks a large flat one)
- ✓ Each tracked tool links to its official docs / getting-started — Phase 1 (docs-link fallback chain: homepage → README scan → honest "repo" label)
- ✓ Local web dashboard with sort-by-velocity and click-through to source — Phase 1 (FastAPI + Jinja2 + htmx; browse-by-section still Active, pending Phase 2 sections)
- ✓ Deterministic pre-ranking gate ahead of any LLM spend — Phase 1 (scorer + absolute floor gate the pipeline before enrichment exists)

### Active

- [ ] Collect items daily from multiple sources (GitHub live in Phase 1; Hacker News, vendor changelogs, package registries, RSS in Phase 3)
- [ ] LLM summarizes each surviving item into a two-line "what this is / why it matters" (Phase 2)
- [ ] LLM auto-assigns each item to exactly one of seven sections (Phase 2)
- [ ] Dashboard browse by section (Phase 2 — needs LLM section assignment)
- [ ] Runs on a daily schedule so the dashboard is current when opened (Phase 4)

### Out of Scope

- Publishing / newsletter / public site — personal tool only, no presentation or cadence commitments
- Multi-user, auth, accounts — single local user
- Medium as a primary signal source — no real API, hidden engagement numbers, heavily SEO-farmed content in this domain; acceptable only as supplementary RSS
- Tracking technology outside AI/LLM/agentic coding — "technology trends" broadly is untractable; the narrow slice is the point
- X/Twitter as a source — API cost is disproportionate to signal gained
- Summarizing every collected item on every run — rejected on cost; deterministic ranking gates LLM spend

## Context

**The three signal types this conflates deliberately, and must keep distinct:**

1. **Releases** — what is newly available (Claude Code features, GSD, Superpowers, MCP servers, model launches). Factual, changelog-shaped.
2. **Traction** — what is actually being adopted (star velocity, download curves, issue/PR activity). Measurable.
3. **Discourse** — what people are discussing (HN threads, Reddit, articles). Noisy, hardest to source well.

**Section taxonomy (7, fixed for v1):**

| Section | What lands here |
|---|---|
| Agentic coding tools | Claude Code, Cursor, Codex, Aider, GSD, Superpowers |
| Models & releases | New model launches, capability/pricing changes, benchmarks |
| Agent frameworks | LangGraph, CrewAI, Agent SDKs, orchestration libs |
| Protocols & interop | MCP servers, tool-calling standards, A2A |
| Safety & guardrails | Guardrails AI, evals, LLM-as-judge, red-teaming |
| RAG & context | Vector stores, retrieval, long-context techniques |
| Local & inference | Ollama, llama.cpp, quantization, serving |

Taxonomy test: a new item should have exactly one obvious home. Revisit if classification error is high in practice.

**Candidate high-signal sources** (to be confirmed by research): GitHub trending / star-history / OSS Insight, Hacker News Algolia API (free, clean), r/LocalLLaMA and r/ChatGPTCoding, vendor changelogs (Anthropic, OpenAI, Google), npm / PyPI download velocity, arXiv cs.SE + cs.CL, Product Hunt, awesome-lists.

**Origin:** The owner wants to track what is getting traction — Claude Code, GSD, Superpowers, Guardrails AI were the named examples — and found the space too broad to follow manually.

## Constraints

- **Scope**: AI/LLM/agentic coding only — narrowness is a deliberate design constraint, not a limitation to grow out of
- **Cost**: LLM spend must be bounded per run — deterministic ranking gates what reaches the model
- **Deployment**: Local single-user; no hosting, auth, or multi-tenancy
- **Scheduling**: Requires a background scheduler for the daily pull
- **Tech stack**: Undecided — deferred to research

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Rank by velocity, not absolute popularity | Absolute star counts measure history, not current traction; a dead 40k-star repo is noise. Momentum is the actual signal. Baked into core, not bolted on. | ✓ Implemented Phase 1 — floor-before-Wilson scorer, unit-verified at the load-bearing boundary |
| Seven fixed sections as v1 taxonomy | Clear boundaries; each item has one obvious home. Broad enough to cover the space, narrow enough to be meaningful. | — Pending (Phase 2 LLM section assignment) |
| Medium deprioritized as a source | No real API, hidden engagement metrics, heavily SEO-farmed in this domain. HN/GitHub/Reddit carry far more signal per unit of effort. | — Pending (Phase 3 sources) |
| Local web dashboard over markdown or CLI | Browsing, sorting by velocity, and clicking through to sources are the primary interactions; a dashboard fits them best despite higher build cost. | ✓ Implemented Phase 1 — FastAPI + Jinja2 + htmx dashboard live |
| LLM summarizes only items clearing a ranking threshold | Summarizing 150–300 items/day is disproportionately expensive for the same readable output. Threshold is config, not architecture. | — Pending (Phase 2 enrichment) |
| Stack deferred to research | No existing constraints or codebase to honor; let current ecosystem evidence decide. | ✓ Resolved — Python 3.12 + SQLite (WAL) + FastAPI/Jinja2/htmx + httpx/hishel/tenacity (see CLAUDE.md stack) |
| Scheduled daily pull (not manual refresh) | The value is the dashboard being current when opened, without the user remembering to trigger it. | — Pending (Phase 4) |
| D-08a: honest day-one empty state over a faked ranked list | On day one every entity has < 2 days of history and falls below the window-gain floor, so `query_ranked` legitimately returns 0 rows. Rather than fabricate a ranking or look broken, the dashboard renders a truthful "still building history" state. | ✓ Implemented Phase 1 — live-verified against real DB (106 entities, 0 eligible) |
| D-16: 4-tier health-strip escalation for source freshness/failure | A dead collector must be visible without digging into logs; escalate by staleness and zero-items-vs-trailing-average. | ✓ Implemented Phase 1 — `health.py`, 11+ tier-boundary tests, live-verified |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-13 after Phase 1*
