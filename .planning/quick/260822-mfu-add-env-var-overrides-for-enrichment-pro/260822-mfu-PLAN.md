---
phase: quick-260822-mfu
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - techtrend/config.py
  - tests/test_config.py
  - README.md
  - .env.example
autonomous: true
requirements: []
must_haves:
  truths:
    - "A set, non-empty TECHTREND_ENRICHMENT_MODEL/PROVIDER/BASE_URL env var overrides the config/tracked.toml value returned by load_config()."
    - "An unset or empty-string env var falls back to the tracked.toml value (then the Pydantic default)."
    - "Only the three enrichment fields are env-overridable; other tunables and secrets are untouched."
  artifacts:
    - techtrend/config.py
    - tests/test_config.py
    - README.md
    - .env.example
  key_links:
    - "load_config() applies env overrides into raw['tunables'] AFTER tomllib.load and BEFORE Config.model_validate(raw)."
---

<objective>
Add optional environment-variable overrides for the three enrichment tunables
(`enrichment_provider`, `enrichment_base_url`, `enrichment_model`) so the model /
provider / endpoint can be set from the Coolify deploy environment without editing
or committing `config/tracked.toml`.

Purpose: Change the enrichment model from the hosting environment (Coolify env vars)
without a code change or a tracked.toml commit.
Output: env-override logic in `load_config()`, a `tests/test_config.py` proving the
override + fallback behavior, and docs (README `## Configure` + `.env.example`).
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@techtrend/config.py
@config/tracked.toml
@tests/conftest.py

# Existing load_config() usage pattern (real config, read-only)
@tests/test_enrich.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Apply enrichment env overrides in load_config() + tests</name>
  <files>techtrend/config.py, tests/test_config.py</files>
  <behavior>
    - With TECHTREND_ENRICHMENT_MODEL set to a non-empty value (monkeypatch),
      load_config() returns tunables.enrichment_model equal to that value.
    - Same for TECHTREND_ENRICHMENT_PROVIDER -> tunables.enrichment_provider and
      TECHTREND_ENRICHMENT_BASE_URL -> tunables.enrichment_base_url.
    - With all three unset, load_config() returns the tracked.toml values
      (enrichment_model == "glm-4.7-flash", enrichment_provider == "openai",
      enrichment_base_url == "https://api.z.ai/api/paas/v4/").
    - An empty-string env var ("") is treated as unset: falls back to the
      tracked.toml value, NOT "".
    - Overrides do not affect any other tunable (e.g. enrichment_cap,
      window_days stay at their tracked.toml values when the three env vars are set).
  </behavior>
  <action>
    In `techtrend/config.py`: add `import os` (alongside `import tomllib`). In
    `load_config()`, AFTER `raw = tomllib.load(f)` and BEFORE
    `Config.model_validate(raw)`, insert env-override logic that maps exactly three
    environment variables into the raw `[tunables]` dict so they pass through Pydantic
    validation:
      - TECHTREND_ENRICHMENT_PROVIDER -> tunables["enrichment_provider"]
      - TECHTREND_ENRICHMENT_BASE_URL -> tunables["enrichment_base_url"]
      - TECHTREND_ENRICHMENT_MODEL    -> tunables["enrichment_model"]
    Use `tunables = raw.setdefault("tunables", {})` so it works even when the TOML
    omits a [tunables] table. For each mapping, read the env var; only write it into
    the dict when the value is set AND non-empty after checking truthiness (an unset
    var returns None, an empty string is falsy) — so a set, non-empty env var wins,
    while unset or empty-string falls back to the file value (then the model default).
    Keep this to these three fields ONLY: do NOT add overrides for any other tunable,
    do NOT read or touch any secret (OPENAI_API_KEY / ANTHROPIC_API_KEY stay read only
    in the provider module), and do NOT change tracked.toml's values. Add a short
    comment noting env wins over tracked.toml for these three enrichment fields.

    Create `tests/test_config.py` covering the behaviors above. Use pytest's
    `monkeypatch.setenv` / `monkeypatch.delenv(..., raising=False)` for the three env
    vars, and call `load_config()` against the real repo `config/tracked.toml`
    (read-only — never mutate it). Assert the override, the unset-fallback, the
    empty-string-as-unset, and that an unrelated tunable is unaffected. Do not require
    network or a database; these tests only exercise config loading.
  </action>
  <verify>
    <automated>python -m pytest tests/test_config.py -q</automated>
    <automated>python -c "import os; os.environ['TECHTREND_ENRICHMENT_MODEL']='test-model'; from techtrend.config import load_config; assert load_config().tunables.enrichment_model=='test-model'"</automated>
    <automated>python -c "from techtrend.config import load_config; print(load_config().tunables.enrichment_model)"</automated>
  </verify>
  <done>
    load_config() returns the env-overridden value for each of the three enrichment
    fields when its env var is set non-empty, and the tracked.toml value
    (enrichment_model == "glm-4.7-flash") when unset or empty. No other tunable or
    secret is affected. tests/test_config.py passes. Committed atomically:
    feat(quick-260822-mfu): env overrides for enrichment provider/model/base_url.
  </done>
</task>

<task type="auto">
  <name>Task 2: Document the three env vars (README + .env.example)</name>
  <files>README.md, .env.example</files>
  <action>
    In `README.md` under `## Configure` (near the existing "Enrichment provider"
    and TECHTREND_DISABLE_LLM bullets), document the three optional env vars —
    `TECHTREND_ENRICHMENT_PROVIDER`, `TECHTREND_ENRICHMENT_BASE_URL`,
    `TECHTREND_ENRICHMENT_MODEL` — stating that when set (non-empty) each wins over
    the corresponding `[tunables]` value in `config/tracked.toml`, so the enrichment
    model / provider / endpoint can be changed from the deploy environment (Coolify)
    without a code change or a tracked.toml commit; unset or empty falls back to the
    file value. Keep it consistent in tone with the surrounding bullets.

    In `.env.example`, add three commented (leading `#`) example lines for the same
    three vars, each with a one-line note that it overrides the tracked.toml enrichment
    setting when set. Place them near the enrichment-related keys. Do not add any real
    secret value and do not uncomment them.
  </action>
  <verify>
    <automated>grep -q "TECHTREND_ENRICHMENT_MODEL" README.md && grep -q "TECHTREND_ENRICHMENT_PROVIDER" README.md && grep -q "TECHTREND_ENRICHMENT_BASE_URL" README.md && echo README-OK</automated>
    <automated>grep -c "TECHTREND_ENRICHMENT_" .env.example</automated>
  </verify>
  <done>
    README `## Configure` documents all three env vars (env wins over tracked.toml
    when set); `.env.example` has three commented example lines for them. Committed
    atomically: docs(quick-260822-mfu): document enrichment env overrides.
  </done>
</task>

</tasks>

<verification>
- Network-free: no test or verify step makes an HTTP call or requires a database.
- `python -c "import os; os.environ['TECHTREND_ENRICHMENT_MODEL']='test-model'; from techtrend.config import load_config; assert load_config().tunables.enrichment_model=='test-model'"` exits 0.
- `python -c "from techtrend.config import load_config; print(load_config().tunables.enrichment_model)"` (no env) prints `glm-4.7-flash`.
- `python -m pytest tests/test_config.py -q` passes.
</verification>

<success_criteria>
- The three enrichment tunables are overridable from environment variables; a set,
  non-empty env var wins over tracked.toml, unset/empty falls back.
- No other tunable, no secret, and tracked.toml's values are unchanged.
- Tests and docs land as two atomic commits.
</success_criteria>

<output>
Create `.planning/quick/260822-mfu-add-env-var-overrides-for-enrichment-pro/260822-mfu-SUMMARY.md` when done.
</output>
