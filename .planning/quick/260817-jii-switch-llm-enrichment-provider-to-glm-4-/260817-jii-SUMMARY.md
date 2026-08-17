---
phase: quick-260817-jii
plan: 01
subsystem: config
tags: [config, llm-enrichment, glm, zai, tunables]
dependency-graph:
  requires: [260817-09l]
  provides: [glm-4.7-flash-enrichment-config]
  affects: [techtrend/pipeline/enrich.py, techtrend/pipeline/llm_openai.py]
tech-stack:
  added: []
  patterns: ["Config-only provider switch reusing the existing openai-compatible provider path"]
key-files:
  created: []
  modified:
    - config/tracked.toml
decisions:
  - "Enrichment moved from Claude Haiku 4.5 to GLM-4.7-Flash (Zhipu/Z.ai) per owner's explicit override of the CLAUDE.md tech-stack table — deliberate, not accidental drift"
  - "Reused the openai-compatible provider path built in quick task 260817-09l (enrichment_provider/enrichment_base_url already existed in techtrend/config.py) — zero Python changes needed"
  - "Secret (Z.ai API key) stays exclusively in gitignored .env, read at runtime by llm_openai.py; tracked.toml carries only provider/model/base_url, never the key value"
metrics:
  duration: 10min
  completed: 2026-08-17
status: complete
---

# Quick Task 260817-jii: Switch LLM enrichment provider to GLM-4.7-Flash Summary

Switched the daily enrichment (summarize+classify) LLM call from Claude Haiku 4.5 to GLM-4.7-Flash (Zhipu/Z.ai) by editing three `[tunables]` keys in `config/tracked.toml` — no Python code changed.

## What Changed

- `enrichment_model`: `"claude-haiku-4-5"` → `"glm-4.7-flash"`
- `enrichment_provider`: added, set to `"openai"` (selects the existing OpenAI-compatible provider path in `techtrend/pipeline/llm_openai.py`, dispatched from `techtrend/pipeline/enrich.py`)
- `enrichment_base_url`: added, set to `"https://api.z.ai/api/paas/v4/"` (Zhipu/Z.ai's OpenAI-compatible GLM endpoint)
- Rewrote the comment above `enrichment_model` to be provider-agnostic (previously described a Claude-specific model)
- Added explanatory comments above `enrichment_provider` and `enrichment_base_url` describing their role and confirming the secret is read from the untracked `.env` at runtime, never stored in this file

This was possible as a config-only change because quick task 260817-09l had already built and tested the OpenAI-compatible provider path (originally for Kimi/Moonshot) — `enrichment_provider`, `enrichment_base_url`, and the `enrich.py` dispatch logic all pre-existed in `techtrend/config.py`. GLM-4.7-Flash was pointed at through the same path by supplying Z.ai's endpoint.

## Verification

- `load_config()` confirmed: `openai glm-4.7-flash https://api.z.ai/api/paas/v4/` — matches required output exactly.
- `pytest tests/test_llm_openai.py -q` — 5 passed, openai provider path regression-clean.
- `git diff --name-only -- '*.py'` — empty; zero Python files touched.
- Full diff manually reviewed — only comment/value changes in `config/tracked.toml`; no secret value present anywhere.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — this plan reused an existing, already-threat-modeled provider path (T-jii-01/T-jii-02 addressed by design: secret never leaves `.env`, base_url is an owner-authored trusted endpoint).

## Self-Check: PASSED

- FOUND: config/tracked.toml (modified, verified via git diff)
- FOUND: cc39a9f (commit exists in git log)
