---
phase: quick-260817-jii
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - config/tracked.toml
autonomous: true
requirements: []
user_setup:
  - service: zhipu-zai
    why: "GLM-4.7-Flash enrichment call authenticates against Z.ai's OpenAI-compatible endpoint"
    env_vars:
      - name: OPENAI_API_KEY
        source: "Z.ai / Zhipu API key — ALREADY placed in .env (gitignored). No action needed unless the run fails auth. NEVER echo, print, or commit this value."

must_haves:
  truths:
    - "load_config().tunables reports provider=openai, model=glm-4.7-flash, base_url=https://api.z.ai/api/paas/v4/"
    - "The existing openai provider path (tests/test_llm_openai.py) still passes unchanged"
    - "No .py file is modified — the change is confined to config/tracked.toml"
    - "No secret key value appears in any tracked/committed file"
  artifacts:
    - "config/tracked.toml (edited [tunables] section)"
  key_links:
    - "config/tracked.toml [tunables] → techtrend/config.py::Tunables → techtrend/pipeline/enrich.py::run_enrichment dispatch on enrichment_provider → techtrend/pipeline/llm_openai.py"
---

<objective>
Switch the daily enrichment (summarize+classify) LLM call from Claude Haiku 4.5 to GLM-4.7-Flash (Zhipu / Z.ai) via the already-built OpenAI-compatible provider path. Zhipu's GLM API is OpenAI-compatible and `enrich.py` already dispatches to `llm_openai.py` when `enrichment_provider == "openai"`, so this is a CONFIG-ONLY change.

Purpose: Move enrichment to GLM-4.7-Flash per the owner's explicit decision (deliberately overriding the CLAUDE.md tech-stack table, which still names Claude Haiku 4.5 for this call). No Python change, no new dependency.
Output: Edited `[tunables]` section of `config/tracked.toml`.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@config/tracked.toml
@techtrend/config.py

# Reference only — these files are REUSED AS-IS and MUST NOT be modified:
# techtrend/pipeline/enrich.py       (dispatches on enrichment_provider)
# techtrend/pipeline/llm_openai.py   (reads OPENAI_API_KEY from .env internally)
# tests/test_llm_openai.py           (regression coverage for the openai path)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Point [tunables] at GLM-4.7-Flash via the openai provider path</name>
  <files>config/tracked.toml</files>
  <action>
Edit ONLY the `[tunables]` section of config/tracked.toml. Make exactly these changes:

1. Change the `enrichment_model` value from `"claude-haiku-4-5"` to `"glm-4.7-flash"`.

2. Add a new key `enrichment_provider = "openai"`.

3. Add a new key `enrichment_base_url = "https://api.z.ai/api/paas/v4/"`.

4. Rewrite the existing comment above `enrichment_model` so it no longer describes a Claude-specific model. It is now a provider-agnostic model id whose meaning depends on `enrichment_provider`. State that the cheapest model that clears the two-line-summary + one-of-seven-label bar is preferred, and that only this value is upgraded if borderline classification proves weak.

5. Add a brief comment above `enrichment_provider` explaining it selects which LLM backend handles the summarize+classify call ("anthropic" = Claude via the anthropic SDK; "openai" = any OpenAI-compatible endpoint), and that this project uses "openai" to reach Zhipu / Z.ai's GLM API.

6. Add a brief comment above `enrichment_base_url` naming it as the OpenAI-compatible endpoint used when `enrichment_provider == "openai"`, pointing at Z.ai's GLM API. In that comment, note that the API secret is read at runtime from the untracked `.env` file by the provider module and is intentionally NOT stored here.

HARD CONSTRAINTS:
- Do NOT modify any `.py` file. All three Tunables fields already exist in techtrend/config.py with defaults; no code change is required or permitted.
- Do NOT write, paste, echo, or otherwise reproduce the Z.ai / OPENAI_API_KEY secret value anywhere — not in tracked.toml, not in a comment, not in any command output. The secret already lives in the gitignored `.env`.
- Keep TOML syntax valid: string values double-quoted, new keys placed inside the `[tunables]` table (before the first `[[sections]]` table).
  </action>
  <verify>
    <automated>python -c "from techtrend.config import load_config; c=load_config(); assert (c.tunables.enrichment_provider, c.tunables.enrichment_model, c.tunables.enrichment_base_url) == ('openai', 'glm-4.7-flash', 'https://api.z.ai/api/paas/v4/'), (c.tunables.enrichment_provider, c.tunables.enrichment_model, c.tunables.enrichment_base_url); print('OK', c.tunables.enrichment_provider, c.tunables.enrichment_model, c.tunables.enrichment_base_url)"</automated>
    <automated>python -m pytest tests/test_llm_openai.py -q</automated>
    <automated>git diff --name-only -- '*.py' | grep -c . | grep -qx 0 && echo "OK: no .py files in diff"</automated>
  </verify>
  <done>
- `load_config()` prints `OK openai glm-4.7-flash https://api.z.ai/api/paas/v4/`.
- `tests/test_llm_openai.py` passes (openai provider path unaffected).
- `git diff` touches only `config/tracked.toml`; zero `.py` files appear in the diff.
- No secret key value is present anywhere in the diff.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| config file → committed git history | A misplaced secret in tracked.toml would leak the Z.ai API key into version control |
| tracked.toml → runtime provider (llm_openai.py) | Config selects the LLM backend and endpoint; the secret crosses only via `.env`, never via config |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-jii-01 | Information Disclosure | config/tracked.toml (committed) | high | mitigate | Key value NEVER written to tracked.toml or any committed file; secret stays in gitignored `.env` and is read only inside llm_openai.py. Verify step confirms no `.py` change and diff is config-only. |
| T-jii-02 | Tampering | new base_url pointing to an untrusted host | low | accept | base_url is the owner-authored official Z.ai GLM endpoint; single-user tool, owner controls the config. |
</threat_model>

<verification>
- `python -c "..."` (Task 1) confirms the three Tunables values resolve through techtrend.config.
- `python -m pytest tests/test_llm_openai.py -q` confirms the reused openai provider path still passes.
- `git diff --name-only` confirms only `config/tracked.toml` changed and no `.py` file is touched.
- Manual scan of `git diff` confirms no secret key value is present.
</verification>

<success_criteria>
- enrichment_provider="openai", enrichment_model="glm-4.7-flash", enrichment_base_url="https://api.z.ai/api/paas/v4/" load cleanly via load_config().
- Existing openai-path tests green.
- Diff is config-only; no Python change; no secret committed.
</success_criteria>

<output>
Create `.planning/quick/260817-jii-switch-llm-enrichment-provider-to-glm-4-/260817-jii-SUMMARY.md` when done.
</output>
