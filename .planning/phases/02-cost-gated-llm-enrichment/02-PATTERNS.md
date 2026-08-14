# Phase 2: Cost-Gated LLM Enrichment - Pattern Map

**Mapped:** 2026-08-14
**Files analyzed:** 11 new, 5 modified
**Analogs found:** 16 / 16

**Drift confirmed against RESEARCH.md:** `techtrend/pipeline/orchestrator.py` contains only `run_collection()` + `record_stage()`/`StageResult` — there is no stage chain to insert into. `techtrend/score.py` is a standalone `python -m techtrend.score` entry point, never called by `ingest.py`. Phase 2 must add a **third** standalone entry point `techtrend/enrich.py` mirroring `score.py` exactly. Confirmed: `GitHubCollector._collect_repo()` fetches `description`/`readme_text` but `identity.py::resolve_entity()` never persists them — enrichment must re-fetch grounding text itself.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `techtrend/enrich.py` | entry point / controller | request-response (batch run) | `techtrend/score.py` | exact |
| `techtrend/pipeline/enrich.py` | service (orchestration loop) | batch / CRUD | `techtrend/pipeline/orchestrator.py::run_collection` | role-match |
| `techtrend/pipeline/grounding.py` | service (fetch + transform) | file-I/O / transform | `techtrend/collectors/github.py` (`_get_readme_text`, `_get_metadata`) | exact |
| `techtrend/pipeline/llm.py` | service (external API client) | request-response | `techtrend/collectors/http.py::build_client` (optional-client injection, env-var isolation) | role-match |
| `techtrend/db/schema.sql` (extended) | model / migration | CRUD | existing `scores` table DDL | exact |
| `techtrend/db/connection.py` | unchanged (reused) | CRUD | n/a — no change needed, `init_db()` already re-runs `schema.sql` | exact |
| `techtrend/server/queries.py::query_ranked` (extended) | query / service | CRUD (read) | itself — `query_ranked` + `query_partial_history_count` (`MAX(run_date)` subquery idiom) | exact |
| `techtrend/server/queries.py::query_section_counts` (new fn) | query / service | CRUD (read) | `query_partial_history_count` (same WHERE-clause / GROUP BY shape) | exact |
| `techtrend/config.py` (extended `Tunables`) | config model | CRUD | itself — `Tunables` Pydantic model | exact |
| `techtrend/server/app.py` (extended route) | controller | request-response | itself — `dashboard()` route | exact |
| `techtrend/web/templates/partials/sidebar.html` | component (template partial) | request-response | `techtrend/web/templates/partials/table.html` (htmx sort-link pattern) | role-match |
| `techtrend/web/templates/partials/table.html` (extended) | component (template partial) | request-response | itself | exact |
| `techtrend/web/templates/dashboard.html` (extended) | component (template) | request-response | itself | exact |
| `config/tracked.toml` (extended, `[[sections]]`) | config | CRUD | existing `[seed]`/`[discovery]` tables | exact |
| `tests/test_enrich.py` | test | — | `tests/test_dashboard.py` (fixture/conn style) — verify at implementation time | role-match |
| `tests/test_grounding.py`, `tests/test_llm.py` | test | — | existing `tests/` fixture conventions (mock `httpx.MockTransport`, injected fake client) | role-match |

## Pattern Assignments

### `techtrend/enrich.py` (entry point, request-response/batch)

**Analog:** `techtrend/score.py` (full file, 79 lines — read in one pass)

**Full shape to copy verbatim, substituting the stage body:**
```python
"""Enrich entry point: `python -m techtrend.enrich`.

Sequence: setup_logging() -> load_config() -> connect()+init_db() ->
run_enrichment(...) -> record_stage('enrich', ...) -> commit -> return 0.
Reuses `record_stage` from `techtrend.pipeline.orchestrator` -- one writer,
one shape, same as score.py's precedent.
"""

import logging
from datetime import UTC, datetime

from techtrend.config import load_config
from techtrend.db.connection import connect, init_db
from techtrend.logging_setup import setup_logging
from techtrend.pipeline.orchestrator import record_stage
from techtrend.pipeline.enrich import run_enrichment

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    config = load_config()
    conn = connect()
    init_db(conn)

    run_date = datetime.now(UTC).date()
    run_date_str = run_date.isoformat()
    started_at = _now_iso()

    try:
        written = run_enrichment(conn, config, run_date)
        status = "success" if written > 0 else "zero_items"
        record_stage(
            conn, run_date_str, "enrich", status,
            item_count=written, started_at=started_at, finished_at=_now_iso(),
        )
        conn.commit()
        logger.info("stage=enrich status=%s items=%d", status, written)
        return 0
    except Exception as exc:  # noqa: BLE001 - an enrichment failure must never be silent (D-10)
        error_detail = str(exc)
        logger.exception("stage=enrich status=failed error=%s", error_detail)
        record_stage(
            conn, run_date_str, "enrich", "failed",
            item_count=0, error_detail=error_detail,
            started_at=started_at, finished_at=_now_iso(),
        )
        conn.commit()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
```

**Key convention:** exit code 0 even on `zero_items`; exit code 1 only on unhandled exception (matches `score.py`'s "stale scores/enrichments after a failed run must leave a visible trace" precedent). `record_stage` is source/stage-agnostic and reused as-is — do not write a second run_manifest writer.

---

### `techtrend/pipeline/enrich.py` (orchestration loop, batch)

**Analog:** `techtrend/pipeline/orchestrator.py::run_collection` (lines 82-147) — per-item try/except isolation pattern; and `techtrend/server/queries.py::query_ranked` (lines 45-73) for the candidate-selection SQL shape.

**Per-item failure isolation pattern to copy** (from `run_collection`, lines 97-146):
```python
for collector in collectors:
    stage = f"collect:{collector.source_id}"
    started_at = _now_iso()
    try:
        # ... work ...
        record_stage(conn, run_date_str, stage, status, item_count=..., ...)
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - one dead source never aborts the run
        logger.warning("stage=%s status=failed error=%s note=...", stage, str(exc))
        record_stage(conn, run_date_str, stage, "failed", item_count=0, error_detail=str(exc), ...)
        conn.commit()
```
Apply the same shape **per candidate entity** in the enrichment loop: one entity's fetch/LLM failure writes a `enrichments` tombstone row and `continue`s to the next candidate — it must never abort the whole `run_enrichment` call (D-10).

**Candidate-selection query to copy the shape of** (`query_ranked`, `server/queries.py` lines 45-73 — reuse the exact `eligible=1 AND score_version=CURRENT AND run_date=MAX(...)` WHERE clause, add `ORDER BY scores.wilson_lower_bound DESC LIMIT :cap` per D-04/D-05/A6):
```sql
SELECT entities.id AS entity_id, entities.full_name, ...
FROM entities
JOIN scores ON scores.entity_id = entities.id
WHERE scores.score_version = :score_version
  AND scores.eligible = 1
  AND scores.run_date = (
      SELECT MAX(latest.run_date) FROM scores AS latest
      WHERE latest.score_version = :score_version
  )
ORDER BY scores.wilson_lower_bound DESC, entities.id ASC
LIMIT :enrichment_cap
```
Import `CURRENT_SCORE_VERSION` from `techtrend.pipeline.score` exactly as `queries.py` does (line 31).

**Cache check / hash helper to copy** (from RESEARCH.md's verified code example, consistent with codebase upsert style):
```python
import hashlib

def _content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

def _cache_hit(conn, entity_id: int, content_hash: str) -> bool:
    row = conn.execute(
        "SELECT id FROM enrichments WHERE entity_id = ? AND content_hash = ? "
        "AND status = 'complete'",
        (entity_id, content_hash),
    ).fetchone()
    return row is not None
```

---

### `techtrend/pipeline/grounding.py` (fetch + transform)

**Analog:** `techtrend/collectors/github.py` — `_get_metadata` (lines 143-147) and `_get_readme_text` (lines 163-176), both tenacity-decorated, both reusing `is_retryable`/`build_client` from `collectors/http.py`.

**Imports pattern to copy** (`github.py` lines 22-30):
```python
import logging
from datetime import date

import httpx
import tenacity

from techtrend.collectors.http import build_client, is_retryable

logger = logging.getLogger(__name__)

GITHUB_API_ROOT = "https://api.github.com"

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(5),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=60),
    "retry": tenacity.retry_if_exception(is_retryable),
}
```

**Fetch pattern to copy** (`_get_readme_text`, lines 163-176 — note the explicit 404-as-None handling, distinct from a retryable error):
```python
@tenacity.retry(**_RETRY_KWARGS)
def _get_readme_text(client: httpx.Client, full_name: str) -> str | None:
    try:
        resp = client.get(
            f"{GITHUB_API_ROOT}/repos/{full_name}/readme",
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise
```
Reuse `build_client()` (do **not** re-read `GITHUB_TOKEN` — that env var stays isolated to `collectors/http.py` per T-01-12, enforced by the existing acceptance-criteria grep). Grounding fetch is a **new client call**, not a collector — no `CollectedItem`/snapshot write.

**Optional-client injection pattern to copy** (`GitHubCollector.__init__`, `github.py` lines 184-189 — the exact seam RESEARCH.md's Wave-0 test plan says to reuse for `tests/test_llm.py`'s fake client injection):
```python
def __init__(self, config: Config | None = None, client: httpx.Client | None = None):
    # Both optional so callers can construct at import time with no side
    # effects -- config/client are resolved lazily inside fetch(), never
    # at construction. Tests inject a fake/mock client this way.
    self._config = config
    self._client = client
```

**Extraction/normalization code** — take verbatim from RESEARCH.md's verified `extract_intro`/`normalize_for_hash` (Code Examples section); no closer in-repo analog exists since no prior module does markdown truncation. Cite Common Pitfall 1 (badge-churn cache defeat) in the docstring, matching the codebase's convention of citing pitfall/requirement IDs in module docstrings (see every file read this session).

---

### `techtrend/pipeline/llm.py` (Anthropic client wrapper)

**Analog:** `techtrend/collectors/http.py::build_client` (lines 66-91) for the optional-client-injection + env-var-isolation pattern; RESEARCH.md Pattern 2 for the exact `messages.parse()` call shape (already verified against the bundled `claude-api` skill).

**Env-var isolation pattern to copy** (`http.py` lines 43-63 — mirror this exactly for `ANTHROPIC_API_KEY`, confining the literal to this one file, matching the `GITHUB_TOKEN` precedent enforced by an acceptance-criteria grep):
```python
class MissingAnthropicKeyError(RuntimeError):
    """Raised at startup when ANTHROPIC_API_KEY is absent from the environment/.env.
    Never silently skips enrichment -- that failure mode is invisible.
    """

def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise MissingAnthropicKeyError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add a key."
        )
    return key
```

**Client construction — optional-injection pattern to copy** (mirrors `build_client(transport=None, ...)`'s test-injection seam):
```python
def build_llm_client(*, client: "anthropic.Anthropic | None" = None) -> "anthropic.Anthropic":
    if client is not None:
        return client
    return anthropic.Anthropic(api_key=_get_api_key())
```

**Structured-output call — copy from RESEARCH.md Pattern 2 verbatim** (already verified against the bundled `claude-api` skill this session; includes the per-request `StrEnum` for the 7-section enforcement, refusal handling, XML-delimited anti-injection prompt). Do not hand-roll retry — the `anthropic` SDK retries 429/5xx internally (CLAUDE.md "What NOT to Use").

**Do NOT wrap the `messages.parse()` call in `tenacity`** — this is an explicit anti-pattern per CLAUDE.md and RESEARCH.md's "Don't Hand-Roll" table, unlike the GitHub HTTP calls in `grounding.py` which DO need `tenacity` (different external service, different retry contract).

---

### `techtrend/db/schema.sql` (extended — `enrichments` table)

**Analog:** existing `scores` table DDL (`schema.sql` lines 35-44) and its `run_manifest` composite-PK precedent (lines 46-55).

**DDL to add** (copy the file's existing conventions: `CREATE TABLE IF NOT EXISTS`, inline comment per column referencing the decision ID, `REFERENCES entities(id)`):
```sql
CREATE TABLE IF NOT EXISTS enrichments (
    id INTEGER PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    content_hash TEXT,                 -- NULL only when status='fetch_failed'
    status TEXT NOT NULL,              -- 'complete' | 'fetch_failed'
    summary_line_1 TEXT,
    summary_line_2 TEXT,
    section TEXT,
    confidence TEXT,                   -- 'high' | 'medium' | 'low'
    low_confidence INTEGER NOT NULL DEFAULT 0,
    computed_at TEXT NOT NULL,
    UNIQUE(entity_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_enrichments_entity_computed
    ON enrichments(entity_id, computed_at);
```
Comment style must match the file's existing header comment ("Four tables" → becomes "Five tables") — update the file-level docstring comment at the top of `schema.sql` (line 2) when adding the table.

**No change needed to `db/connection.py`** — `init_db()` (lines 36-40) already does `conn.executescript(schema_sql)` against the whole file; the new table is picked up automatically.

---

### `techtrend/server/queries.py::query_ranked` (extended — LEFT JOIN)

**Analog:** itself — extend `_QUERY_RANKED_SQL` (lines 45-74) in place; do not rewrite.

**Exact pattern to extend** — add a `LEFT JOIN enrichments` block using the identical `MAX(...)`-correlated-subquery idiom already used for `scores.run_date`:
```sql
    FROM entities
    JOIN scores ON scores.entity_id = entities.id
    LEFT JOIN enrichments ON enrichments.entity_id = entities.id
        AND enrichments.computed_at = (
            SELECT MAX(e2.computed_at) FROM enrichments AS e2
            WHERE e2.entity_id = entities.id
        )
    WHERE scores.score_version = :score_version
      AND scores.eligible = 1
      AND scores.run_date = ( ... unchanged ... )
      {% if section %}AND enrichments.section = :section{% endif %}
```
Add `section: str | None = None` param to `query_ranked(conn, sort=DEFAULT_SORT, section=None)`, threading it through to the query dict exactly as `sort` is threaded — **do not** interpolate `section` as raw SQL text; bind it as a parameter (same discipline `SORT_KEYS` allow-dict enforces for `sort`, per the module's own T-01-06/T-01-29 warning at lines 9-15).

**New `query_section_counts` — copy the shape of `query_partial_history_count`** (lines 95-122, same `MAX(run_date)`-pinned WHERE clause, same docstring convention citing the requirement ID):
```python
def query_section_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Per-section counts for the sidebar (DASH-02/D-11), pinned to the same
    MAX(run_date)/eligible=1/current-score-version seam as query_ranked, so
    sidebar counts never drift from what the table actually renders.
    """
    rows = conn.execute(
        """
        SELECT enrichments.section AS section, COUNT(*) AS count
        FROM entities
        JOIN scores ON scores.entity_id = entities.id
        JOIN enrichments ON enrichments.entity_id = entities.id
            AND enrichments.computed_at = (
                SELECT MAX(e2.computed_at) FROM enrichments AS e2
                WHERE e2.entity_id = entities.id
            )
        WHERE scores.score_version = :score_version
          AND scores.eligible = 1
          AND enrichments.section IS NOT NULL
          AND scores.run_date = (
              SELECT MAX(latest.run_date) FROM scores AS latest
              WHERE latest.score_version = :score_version
          )
        GROUP BY enrichments.section
        """,
        {"score_version": CURRENT_SCORE_VERSION},
    ).fetchall()
    return {row["section"]: row["count"] for row in rows}
```

---

### `techtrend/config.py` (extended `Tunables`)

**Analog:** itself — `Tunables` class (lines 34-52). Every new field must carry an inline comment citing its decision ID, matching every existing field's convention exactly.

**Fields to add, following the exact style** (`# <purpose> (D-XX)` comment above each field):
```python
class Tunables(BaseModel):
    # ... existing fields unchanged ...

    # Hard per-run cap on enrichment LLM calls, independent of ranking
    # threshold (ENR-02, D-04). Applied to the candidate SET (which entities
    # are even fetched), not just successful LLM calls -- see A6.
    enrichment_cap: int = 15
    # README intro truncation cap in characters, before the first H2+ heading
    # (D-07).
    grounding_char_cap: int = 2000
    # Claude model id for the summarize+classify call (D-03).
    enrichment_model: str = "claude-haiku-4-5"
    # Confidence tier that trips the low-confidence dashboard flag (D-02);
    # enum-only ("high"|"medium"|"low") -- JSON Schema has no numeric range
    # support, see Common Pitfall 2.
    confidence_flag_threshold: str = "low"
```
`Config` model may also gain a `sections: list[SectionDef]` field per A4 (extending `config/tracked.toml` with `[[sections]]`, mirroring `Seed`/`Discovery`'s existing `BaseModel` + `Field(default_factory=...)` pattern at lines 20-26).

---

### `techtrend/server/app.py` (extended route)

**Analog:** itself — `dashboard()` route (lines 40-89).

**Pattern to extend:** add `section: str | None = None` query param to the route signature, thread through to `query_ranked(conn, sort=sort, section=section)`, and pass `query_section_counts(conn)` + `section` into the template context dict (lines 81-88), matching the existing style of adding every new query result as a flat top-level template variable:
```python
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, sort: str = "velocity", section: str | None = None) -> HTMLResponse:
    ...
    rows, applied_sort = query_ranked(conn, sort=sort, section=section)
    section_counts = query_section_counts(conn)
    ...
    return templates.TemplateResponse(request, template_name, {
        "rows": rows,
        "sort": applied_sort,
        "section": section,
        "section_counts": section_counts,
        # ... existing keys unchanged ...
    })
```
The `try/except (sqlite3.Error, OSError, tomllib.TOMLDecodeError, ValueError)` boundary (lines 70-75) must wrap the new query calls too — do not add a second try/except.

---

### `techtrend/web/templates/partials/sidebar.html` (new) + `table.html` (extended)

**Analog:** `table.html`'s sort-header htmx links (lines 6-29).

**Critical cross-file consistency requirement (Pitfall 5, RESEARCH.md):** every htmx link in BOTH files must carry **both** `sort` and `section` current-state values, or clicking one control silently drops the other's active state. Copy this exact link-construction style, extended with both params:
```html
<!-- table.html sort header, extended -->
<a class="sort-link{{ ' sort-active' if sort == 'name' else '' }}"
   hx-get="/?sort=name&section={{ section or '' }}" hx-target="#table-body"
   hx-swap="innerHTML" hx-push-url="true" hx-indicator="#table-body">Repo...</a>

<!-- sidebar.html section link, new -->
<a class="section-link{{ ' section-active' if section == 'agentic_coding_tools' else '' }}"
   hx-get="/?sort={{ sort }}&section=agentic_coding_tools" hx-target="#table-body"
   hx-swap="innerHTML" hx-push-url="true" hx-indicator="#table-body">
   Agentic Coding Tools <span class="section-count">{{ section_counts.get('agentic_coding_tools', 0) }}</span>
</a>
```
Reuse the exact `hx-target="#table-body" hx-swap="innerHTML" hx-push-url="true" hx-indicator="#table-body"` attribute set — every existing sort link uses this identical set (verified across all 4 sort headers, `table.html` lines 6-29); the sidebar must match exactly, not invent a new target/swap convention.

`table.html`'s row rendering (lines 34-46) needs a new cell for `summary_line_1`/`summary_line_2` and the low-confidence flag, plus honest fallback text for unenriched rows (D-10): follow the existing `{{ row['docs_url'] if row['docs_url'] else row['url'] }}` conditional-fallback idiom (line 44) — e.g. `{{ row['summary_line_1'] if row['summary_line_1'] else 'summary pending' }}`. **Jinja2 autoescaping must not be bypassed with `|safe`** on `summary_line_1`/`summary_line_2`/`section` (Security Domain, stored-XSS mitigation) — no existing template in this codebase uses `|safe` anywhere; do not introduce the first instance.

`dashboard.html` needs the sidebar included alongside `health_strip.html` (line 13's `{% include %}` pattern):
```html
{% include "partials/health_strip.html" %}
{% include "partials/sidebar.html" %}
```
Also update the `htmx:responseError`/`htmx:sendError` handlers' `colspan="6"` (lines 31, 38) to the new column count if a summary column is added.

---

## Shared Patterns

### Standalone stage entry point
**Source:** `techtrend/score.py` (whole file)
**Apply to:** `techtrend/enrich.py`
Exact structure: `setup_logging()` → `load_config()` → `connect()`+`init_db()` → stage logic → `record_stage(...)` → `conn.commit()` → return 0/1, with `try/except Exception` wrapping and `finally: conn.close()`. `record_stage` (from `pipeline/orchestrator.py`) is reused as-is — it is already stage/source-agnostic.

### Per-item failure isolation
**Source:** `techtrend/pipeline/orchestrator.py::run_collection` (lines 97-146)
**Apply to:** `techtrend/pipeline/enrich.py`'s per-candidate loop
One entity's fetch/LLM failure is caught, logged (`logger.warning`), recorded, and the loop `continue`s — never aborts the whole run (D-10 is the direct analog of Phase 1's Pitfall 1 isolation).

### `MAX(...)`-correlated-subquery "current row" idiom
**Source:** `techtrend/server/queries.py::query_ranked` / `query_partial_history_count` (lines 45-122)
**Apply to:** the `enrichments` LEFT JOIN, `query_section_counts`, and `pipeline/enrich.py`'s candidate-selection query
Every place that needs "the current row per entity" out of an append-only, composite-keyed table uses this exact subquery shape — never an upsert-in-place row.

### Env-var secret isolation
**Source:** `techtrend/collectors/http.py` (`GITHUB_TOKEN`, lines 43-63)
**Apply to:** `techtrend/pipeline/llm.py` (`ANTHROPIC_API_KEY`)
Read the secret in exactly one module, raise a custom `Missing*Error` at call time (never fall back silently), never log or pass the raw token elsewhere. Enforced by an acceptance-criteria grep confining the literal env var name to one file — the new phase's plan must add an equivalent grep for `ANTHROPIC_API_KEY`.

### Optional-client dependency injection for testability
**Source:** `techtrend/collectors/github.py::GitHubCollector.__init__` (lines 184-189) / `techtrend/collectors/http.py::build_client(transport=None, ...)`
**Apply to:** `pipeline/llm.py::build_llm_client(client=None)`, `pipeline/grounding.py` fetch functions accepting an injected `httpx.Client`
Both optional so tests inject a fake/mock; production omits them and gets the real client, resolved lazily inside the call, never at construction.

### Config-driven tunables, not code constants
**Source:** `techtrend/config.py::Tunables` (lines 34-52)
**Apply to:** all 4 new enrichment knobs
Every field carries an inline comment citing its decision ID, exactly like every existing field.

### Honest degradation over fabrication/hiding
**Source:** `table.html`'s empty-state handling (lines 55-79) and `docs_url` fallback (line 44)
**Apply to:** unenriched-row rendering ("summary pending" / "source unavailable" markers, D-10)
Never a blank cell, never fabricated text — always an explicit, honest fallback string, matching the existing `db_error`/`has_successful_run`/`partial_history_count` empty-state discipline.

## No Analog Found

None — every file identified in CONTEXT.md/RESEARCH.md has a strong existing-code analog verified this session. The Anthropic structured-output call itself (`client.messages.parse`) has no in-repo analog since this is the first LLM integration; use RESEARCH.md's Pattern 2 code example (already verified against the bundled `claude-api` skill) as the authoritative source for that one piece.

## Metadata

**Analog search scope:** `techtrend/` (score.py, pipeline/, collectors/, db/, server/, config.py, web/templates/), `config/tracked.toml`
**Files read this session:** `techtrend/score.py`, `techtrend/pipeline/orchestrator.py`, `techtrend/collectors/http.py`, `techtrend/collectors/github.py`, `techtrend/db/schema.sql`, `techtrend/db/connection.py`, `techtrend/server/queries.py`, `techtrend/config.py`, `techtrend/server/app.py`, `techtrend/web/templates/dashboard.html`, `techtrend/web/templates/partials/table.html`
**Pattern extraction date:** 2026-08-14
