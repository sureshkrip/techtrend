"""Cost-gated enrichment orchestration loop (ENR-01, ENR-02, ENR-05, ENR-06,
DATA-04).

`select_candidates` reuses the exact eligible-set seam
`server/queries.py::query_ranked` reads from (`scores.eligible = 1 AND
score_version = CURRENT_SCORE_VERSION AND run_date = MAX(...)`), ordered by
velocity (`wilson_lower_bound DESC`) with a deterministic `entities.id ASC`
tie-break, and applies the hard per-run cap as a SQL `LIMIT` on the candidate
SET itself -- before any grounding fetch (ENR-02/D-05/A6). The cap gates
which entities are even *fetched*, never merely which ones reach the LLM
after a cache miss: a cache-hit-heavy run must never fetch more than
`enrichment_cap` entities.

`run_enrichment` then loops the candidate set, per entity: fetch grounding
text (skip the LLM entirely on an empty/unfetchable fetch, D-08), compute a
badge/whitespace-normalized content hash, skip the LLM on a cache hit
(DATA-04/D-09/SC4), and otherwise call the LLM and write a 'complete' row or
-- on a refusal -- an honest 'fetch_failed' tombstone. Every per-candidate
step is wrapped in a try/except mirroring
`pipeline/orchestrator.py::run_collection`'s per-collector isolation: one
dead candidate is logged and skipped, never aborts the run, and never drops
the entity's ranked `scores` row (ENR-06/D-10).
"""

import hashlib
import logging
from datetime import UTC, date, datetime

from techtrend.collectors.http import build_client
from techtrend.pipeline.grounding import fetch_grounding, normalize_for_hash
from techtrend.pipeline.llm import build_llm_client, enrich_item
from techtrend.pipeline.score import CURRENT_SCORE_VERSION

logger = logging.getLogger(__name__)

# Mirrors query_ranked's eligible-set WHERE clause (server/queries.py lines
# 45-73) exactly, plus the hard cap applied to the candidate SET (ENR-02/D-05):
# entities.id ASC is the deterministic tie-break when wilson_lower_bound ties.
_SELECT_CANDIDATES_SQL = """
    SELECT
        entities.id AS entity_id,
        entities.full_name,
        scores.wilson_lower_bound
    FROM entities
    JOIN scores ON scores.entity_id = entities.id
    WHERE scores.score_version = :score_version
      AND scores.eligible = 1
      AND scores.run_date = (
          SELECT MAX(latest.run_date)
          FROM scores AS latest
          WHERE latest.score_version = :score_version
      )
    ORDER BY scores.wilson_lower_bound DESC, entities.id ASC
    LIMIT :enrichment_cap
"""


def select_candidates(conn, score_version: int, cap: int):
    """Return up to `cap` eligible entities at `score_version`, highest
    velocity first, deterministic on ties -- the same eligible-set seam
    `query_ranked` reads, with the hard per-run cap applied as a SQL LIMIT
    on the candidate SET before any fetch (ENR-01, ENR-02/D-05/A6).
    """
    return conn.execute(
        _SELECT_CANDIDATES_SQL,
        {"score_version": score_version, "enrichment_cap": cap},
    ).fetchall()


def _content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def _cache_hit(conn, entity_id: int, content_hash: str) -> bool:
    """True when a 'complete' enrichments row already exists for this exact
    (entity, content_hash) pair -- unchanged content never re-calls the LLM
    (DATA-04/D-09/SC4)."""
    row = conn.execute(
        "SELECT id FROM enrichments WHERE entity_id = ? AND content_hash = ? "
        "AND status = 'complete'",
        (entity_id, content_hash),
    ).fetchone()
    return row is not None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_tombstone(conn, entity_id: int) -> None:
    """Record a 'fetch_failed' tombstone (content_hash NULL, D-08/D-10) --
    used both for an unfetchable/empty grounding fetch and for an LLM
    refusal, so an entity that couldn't be summarized this run is never
    silently missing and never fabricated. SQLite treats each NULL as
    distinct under UNIQUE(entity_id, content_hash), so multiple tombstones
    per entity across runs are allowed without conflict."""
    conn.execute(
        """
        INSERT INTO enrichments (
            entity_id, content_hash, status, computed_at
        ) VALUES (?, NULL, 'fetch_failed', ?)
        """,
        (entity_id, _now_iso()),
    )


def _write_complete(conn, entity_id: int, content_hash: str, result, low_confidence: int) -> None:
    """Upsert a 'complete' enrichments row keyed on (entity_id, content_hash)
    -- a re-run that lands on the exact same content hash (e.g. a retried
    run on the same day) replaces the row rather than duplicating it."""
    conn.execute(
        """
        INSERT INTO enrichments (
            entity_id, content_hash, status, summary_line_1, summary_line_2,
            section, confidence, low_confidence, computed_at
        ) VALUES (?, ?, 'complete', ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id, content_hash) DO UPDATE SET
            status = excluded.status,
            summary_line_1 = excluded.summary_line_1,
            summary_line_2 = excluded.summary_line_2,
            section = excluded.section,
            confidence = excluded.confidence,
            low_confidence = excluded.low_confidence,
            computed_at = excluded.computed_at
        """,
        (
            entity_id,
            content_hash,
            result.summary_line_1,
            result.summary_line_2,
            str(result.section),
            str(result.confidence),
            low_confidence,
            _now_iso(),
        ),
    )


def run_enrichment(
    conn,
    config,
    run_date: date,
    fetch_grounding_fn=None,
    content_hash_fn=None,
    llm_call_fn=None,
) -> int:
    """Select eligible candidates up to the hard cap, fetch grounding, skip
    the LLM on a cache hit or an empty/unfetchable fetch, and write a
    'complete' row or an honest 'fetch_failed' tombstone per candidate.

    `fetch_grounding_fn(full_name) -> (description, readme_intro)`,
    `content_hash_fn(description, readme_intro) -> content_hash`, and
    `llm_call_fn(**kwargs) -> EnrichmentResult | None` are injectable seams
    -- tests supply fakes with no live GitHub/Anthropic call; production
    callers omit them and get one real grounding client and one real LLM
    client built up front for the whole run (never per candidate).

    Any per-candidate exception (fetch error, LLM error, refusal -> None) is
    caught, logged, and the loop continues -- one dead candidate never
    aborts the run and never removes the entity's ranked `scores` row
    (ENR-06/D-10). Returns the count of 'complete' rows written this run.
    """
    tunables = config.tunables
    candidates = select_candidates(
        conn, score_version=CURRENT_SCORE_VERSION, cap=tunables.enrichment_cap
    )

    if not candidates:
        # Zero eligible entities -- exit before building any real client, so
        # a zero_items run never requires GITHUB_TOKEN/ANTHROPIC_API_KEY to
        # be set (ENR-01 empty).
        return 0

    if fetch_grounding_fn is None:
        grounding_client = build_client()
        grounding_char_cap = tunables.grounding_char_cap

        def fetch_grounding_fn(full_name):
            result = fetch_grounding(grounding_client, full_name, char_cap=grounding_char_cap)
            if result is None:
                return None, None
            return result

    if content_hash_fn is None:

        def content_hash_fn(description, readme_intro):
            return _content_hash(normalize_for_hash(description, readme_intro))

    if llm_call_fn is None:
        llm_client = build_llm_client()
        section_dicts = [s.model_dump() for s in config.sections]
        enrichment_model = tunables.enrichment_model

        def llm_call_fn(**kwargs):
            return enrich_item(
                llm_client, model=enrichment_model, sections=section_dicts, **kwargs
            )

    written = 0
    for row in candidates:
        entity_id = row["entity_id"]
        full_name = row["full_name"]
        try:
            description, readme_intro = fetch_grounding_fn(full_name)
            if description is None and readme_intro is None:
                _write_tombstone(conn, entity_id)
                conn.commit()
                continue

            content_hash = content_hash_fn(description, readme_intro)
            if _cache_hit(conn, entity_id, content_hash):
                continue

            result = llm_call_fn(description=description, readme_intro=readme_intro)
            if result is None:
                # Refusal -- never fabricate. Same tombstone shape as a
                # fetch failure (D-08/D-10): content_hash stays NULL so the
                # invariant "NULL only when status='fetch_failed'" holds,
                # and the LLM is retried against this content next run.
                _write_tombstone(conn, entity_id)
                conn.commit()
                continue

            low_confidence = 1 if str(result.confidence) == tunables.confidence_flag_threshold else 0
            _write_complete(conn, entity_id, content_hash, result, low_confidence)
            conn.commit()
            written += 1
        except Exception as exc:  # noqa: BLE001 - one dead candidate never aborts the run (D-10)
            logger.warning(
                "entity_id=%s full_name=%s status=failed error=%s "
                "note=candidate skipped, run continues",
                entity_id,
                full_name,
                str(exc),
            )
            continue

    return written
