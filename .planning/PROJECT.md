# TechTrend

## What This Is

A personal, self-updating intelligence dashboard for the AI coding and LLM ecosystem. It pulls daily from high-signal sources (GitHub star velocity, Hacker News, vendor changelogs, package registries, curated RSS), ranks what it finds by *momentum* rather than absolute popularity, has an LLM summarize and file the survivors into seven fixed sections, and links each tracked tool to its official docs. Built for one user — the owner — as a replacement for scrolling social feeds to stay current.

## Core Value

Open it once a day and know, in five minutes, what is actually gaining traction in AI coding — without scrolling social feeds and without missing the thing that matters.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Collect items daily from multiple sources (GitHub, Hacker News, vendor changelogs, package registries, RSS)
- [ ] Rank by velocity/momentum, not absolute counts — a 900-star repo gaining 400/week outranks a dead 40k-star repo
- [ ] LLM summarizes each surviving item into a two-line "what this is / why it matters"
- [ ] LLM auto-assigns each item to exactly one of seven sections
- [ ] Local web dashboard: browse by section, sort by velocity, click through to source
- [ ] Each tracked tool links to its official docs / getting-started
- [ ] Runs on a daily schedule so the dashboard is current when opened
- [ ] Deterministic pre-ranking gates which items reach the LLM (cost control, configurable threshold)

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
| Rank by velocity, not absolute popularity | Absolute star counts measure history, not current traction; a dead 40k-star repo is noise. Momentum is the actual signal. Baked into core, not bolted on. | — Pending |
| Seven fixed sections as v1 taxonomy | Clear boundaries; each item has one obvious home. Broad enough to cover the space, narrow enough to be meaningful. | — Pending |
| Medium deprioritized as a source | No real API, hidden engagement metrics, heavily SEO-farmed in this domain. HN/GitHub/Reddit carry far more signal per unit of effort. | — Pending |
| Local web dashboard over markdown or CLI | Browsing, sorting by velocity, and clicking through to sources are the primary interactions; a dashboard fits them best despite higher build cost. | — Pending |
| LLM summarizes only items clearing a ranking threshold | Summarizing 150–300 items/day is disproportionately expensive for the same readable output. Threshold is config, not architecture. | — Pending |
| Stack deferred to research | No existing constraints or codebase to honor; let current ecosystem evidence decide. | — Pending |
| Scheduled daily pull (not manual refresh) | The value is the dashboard being current when opened, without the user remembering to trigger it. | — Pending |

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
*Last updated: 2026-07-19 after initialization*
