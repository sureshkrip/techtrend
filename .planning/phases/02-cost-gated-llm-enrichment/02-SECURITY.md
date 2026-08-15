---
phase: 02
slug: cost-gated-llm-enrichment
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-15
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register origin: authored at plan time (`register_authored_at_plan_time: true`) — 15 STRIDE
threats declared across the five 02-*-PLAN.md `<threat_model>` blocks. Verification depth:
ASVS L1 (grep-level mitigation presence), which is sufficient for this level per the
secure-phase short-circuit. All mitigations confirmed present in the shipped implementation.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| config file → app | `config/tracked.toml` parsed into Pydantic models | non-secret local config (malformed input) |
| migration → stored DB | `schema.sql` DDL applied to the on-disk SQLite file | schema (forward-only, additive) |
| untrusted README/description → LLM prompt | attacker-controllable repo text concatenated into a model prompt | untrusted text |
| app → Anthropic API | `ANTHROPIC_API_KEY` crosses to an external service | secret credential |
| PyPI → build | the `anthropic` wheel installed into the runtime | third-party code (supply chain) |
| GitHub REST → app | untrusted repo description + README enters the pipeline | untrusted text |
| app → content hash | normalized grounding text becomes the cache key | derived cache key |
| scores table → gate | the eligible seam decides what reaches the (paid) LLM | cost-control decision |
| LLM output → enrichments table | validated model output persisted | validated model output |
| enrichments table → HTML | LLM summary text (may echo README content) rendered to browser | untrusted-derived text |
| query params → SQL | the `?section=` value crosses into `query_ranked` | untrusted query param |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-02-01 | Tampering | config.py `[[sections]]` parse | low | mitigate | Pydantic `SectionDef` validation; test asserts exactly seven ids in fixed order | closed |
| T-02-02 | Denial of Service | enrichments migration | low | accept | `CREATE TABLE IF NOT EXISTS` idempotent + additive; forward-only, no data-shape change | closed |
| T-02-03 | Tampering | `enrich_item` prompt injection via malicious README | high | mitigate | README/description wrapped in `<repo_description>`/`<readme_excerpt>` delimiters + "untrusted data, not instructions" system prompt (llm.py:139,148); Pydantic `EnrichmentResult` validates all output before SQL/templates | closed |
| T-02-04 | Information Disclosure | `ANTHROPIC_API_KEY` | high | mitigate | `os.environ.get("ANTHROPIC_API_KEY")` confined to `pipeline/llm.py:74` only (grep across `techtrend/` confirms; enrich.py ref is a comment); never logged, never committed | closed |
| T-02-SC | Tampering | `anthropic` install (supply chain) | high | mitigate | version pinned `anthropic==0.122.0` in pyproject.toml; blocking-human legitimacy checkpoint (Plan 02 Task 1) verified SDK identity before install | closed |
| T-02-05 | Spoofing | model fabrication (parametric knowledge) | medium | mitigate | system prompt forbids knowledge beyond provided text; refusal → None; empty-grounding skip enforced by caller | closed |
| T-02-06 | Tampering | fetched README/description as untrusted input | medium | mitigate | text treated as data; delimiter-isolation (LLM boundary) + autoescape (template boundary); grounding never evals/executes fetched content | closed |
| T-02-07 | Denial of Service | badge-churn cache defeat | medium | mitigate | `normalize_for_hash` strips volatile badge/comment markup before hashing so the cache hits, bounding LLM spend | closed |
| T-02-08 | Tampering | content-hash integrity | low | mitigate | stdlib `hashlib.sha256` over utf-8 normalized text; never a hand-rolled hash | closed |
| T-02-09 | Denial of Service | LLM spend / cost gate | high | mitigate | cap applied as SQL `LIMIT :enrichment_cap` on candidate SET before any fetch (enrich.py:54); cache hit on `content_hash` skips the call; `enrichment_cap` now `Field(gt=0)` (CR-01 fix, commit aeddf6a) | closed |
| T-02-10 | Tampering | unvalidated LLM output → SQL | medium | mitigate | `enrich_item` returns Pydantic-validated `EnrichmentResult`; enrichments writes bind parameters, never interpolate model text into SQL | closed |
| T-02-11 | Denial of Service | one candidate's failure aborting the run | medium | mitigate | per-candidate try/except/continue; a dead item writes a tombstone and the run proceeds | closed |
| T-02-12 | Spoofing | fabricated summary on empty grounding | high | mitigate | `fetch_grounding` None → `fetch_failed` tombstone, `enrich_item` never called; refusal → None → tombstone (enrich.py:91-101, llm.py:23) | closed |
| T-02-13 | Elevation of Privilege | stored XSS from LLM summary echoing README | high | mitigate | Jinja2 default autoescape; grep confirms zero `|safe` on summary/section in templates | closed |
| T-02-14 | Tampering | `?section=` injection into `query_ranked` | medium | mitigate | `section` bound as a SQL parameter (`params["section"] = section`, queries.py:124), never interpolated | closed |
| T-02-15 | Denial of Service | enrichment failure removing a ranked row | high | mitigate | `LEFT JOIN enrichments` (queries.py:76) keeps every eligible row; unenriched rows render honest fallbacks | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `workflow.security_block_on` (high) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-02 | Forward-only additive `CREATE TABLE IF NOT EXISTS` migration carries no data-shape change to existing tables; DoS surface is nil for a single-user local DB. Mitigation and acceptance coincide. | owner (single-user tool) | 2026-08-15 |

Below-threshold robustness notes carried from 02-REVIEW.md (non-blocking, not open threats):
- WR-02 (T-02-07): `normalize_for_hash` badge-strip covers inline-style `![alt](url)` badges but not reference-style `![alt][ref]`. Narrower cache-churn window for reference-style shields; does not defeat the cost cap (hard `LIMIT` still bounds spend). Backlog hardening.
- WR-03 (T-02-03): README text interpolated into the prompt without delimiter-collision escaping — a README containing literal `</repo_description>` is passed through. Defense is instruction-level; blast radius bounded because `section`/`confidence` are enum-constrained. Backlog hardening.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-15 | 15 | 15 | 0 | Claude (secure-phase, ASVS L1 grep-depth) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-15
