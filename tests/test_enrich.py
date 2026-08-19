"""Enrichment orchestration-loop tests (DATA-04, ENR-01, ENR-02, ENR-05;
02-VALIDATION.md Wave 0).

`techtrend.pipeline.enrich` does not exist yet -- these tests define
`select_candidates`/`run_enrichment`'s contract (eligible-set gate, hard cap,
cache-hit skip, fetch-failure skip) before a later plan implements it.
Seeded against the shared `db` fixture's ephemeral Postgres connection,
mirroring tests/test_dashboard.py's connection/seed style. No live GitHub or
Anthropic call anywhere -- grounding fetch, content-hash computation, and
the LLM call are all injected via optional-parameter seams so the
orchestration logic is testable in isolation. Imports are inside each test
function so `pytest --collect-only` succeeds cleanly at Wave 0.

The `TECHTREND_DISABLE_LLM` tests below (quick task 260818-sbl) live in this
same file since they exercise `techtrend.enrich.main()` -- the module under
test throughout this file -- rather than the pipeline orchestration loop.
"""

from datetime import date

import pytest

from techtrend.pipeline.score import CURRENT_SCORE_VERSION


def _insert_entity(conn, native_id, *, full_name=None):
    full_name = full_name or f"owner/{native_id}"
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, discovery_method,
            admitted_at, last_seen_at
        ) VALUES (
            'github', %(native_id)s, %(full_name)s, %(url)s, 'seed',
            '2026-07-01T00:00:00Z', '2026-07-19T00:00:00Z'
        )
        """,
        {
            "native_id": native_id,
            "full_name": full_name,
            "url": f"https://github.com/{full_name}",
        },
    )
    return conn.execute(
        "SELECT id FROM entities WHERE source = 'github' AND source_native_id = %s",
        (native_id,),
    ).fetchone()["id"]


def _insert_score(
    conn,
    entity_id,
    *,
    run_date="2026-07-19",
    wilson_lower_bound=0.5,
    eligible=1,
    score_version=CURRENT_SCORE_VERSION,
):
    conn.execute(
        """
        INSERT INTO scores (
            entity_id, run_date, score_version, stars_gained,
            window_days, wilson_lower_bound, eligible
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (entity_id, run_date, score_version, 100, 7, wilson_lower_bound, int(eligible)),
    )


# --- ENR-01: gate reads the existing Phase 1 eligible-set seam ---


def test_gate_reads_eligible_seam(db):
    from techtrend.pipeline.enrich import select_candidates

    conn = db
    eligible = _insert_entity(conn, "1", full_name="owner/eligible-repo")
    ineligible = _insert_entity(conn, "2", full_name="owner/ineligible-repo")
    stale = _insert_entity(conn, "3", full_name="owner/stale-version-repo")
    _insert_score(conn, eligible, eligible=1)
    _insert_score(conn, ineligible, eligible=0)
    _insert_score(conn, stale, eligible=1, score_version=CURRENT_SCORE_VERSION - 1)
    conn.commit()

    candidates = select_candidates(conn, score_version=CURRENT_SCORE_VERSION, cap=15)

    full_names = {row["full_name"] for row in candidates}
    assert full_names == {"owner/eligible-repo"}


# --- ENR-02/D-05: hard per-run cap, velocity-first, applied to the candidate SET ---


def test_cap_limits_candidate_set(db):
    from techtrend.pipeline.enrich import select_candidates

    conn = db
    for i in range(1, 6):
        entity_id = _insert_entity(conn, str(i), full_name=f"owner/repo-{i}")
        _insert_score(conn, entity_id, wilson_lower_bound=i / 10, eligible=1)
    conn.commit()

    candidates = select_candidates(conn, score_version=CURRENT_SCORE_VERSION, cap=2)

    assert len(candidates) == 2
    # Velocity-first (D-05): the two highest wilson_lower_bound rows win,
    # the rest stay ranked-but-unenriched, first in line next run.
    assert [row["full_name"] for row in candidates] == ["owner/repo-5", "owner/repo-4"]


def test_enrichment_cap_rejects_non_positive():
    # CR-01: a non-positive cap would defeat SC1's hard cost cap -- Postgres
    # treats a negative LIMIT as an error and NULL/absent LIMIT as
    # unbounded, so the guard must live in config validation, not
    # downstream. Zero is equally invalid (no work, but a bad edit
    # shouldn't silently disable enrichment either).
    import pytest
    from pydantic import ValidationError

    from techtrend.config import Tunables

    Tunables(enrichment_cap=1)  # lower bound is valid
    for bad in (0, -1, -15):
        with pytest.raises(ValidationError):
            Tunables(enrichment_cap=bad)


# --- DATA-04/D-09/SC4: unchanged content_hash -> LLM never re-called ---


def test_cache_hit_skips_llm_call(db):
    from techtrend.config import load_config
    from techtrend.pipeline.enrich import run_enrichment

    conn = db
    entity_id = _insert_entity(conn, "1", full_name="owner/cached-repo")
    _insert_score(conn, entity_id, eligible=1)
    content_hash = "a" * 64
    conn.execute(
        """
        INSERT INTO enrichments (
            entity_id, content_hash, status, summary_line_1, summary_line_2,
            section, confidence, low_confidence, computed_at
        ) VALUES (%s, %s, 'complete', 'line 1', 'line 2', 'agentic_coding_tools', 'high', 0,
                  '2026-07-18T00:00:00Z')
        """,
        (entity_id, content_hash),
    )
    conn.commit()

    llm_calls = []

    def fake_fetch_grounding(full_name):
        return "same description", "same readme intro"

    def fake_content_hash(description, readme_intro):
        return content_hash

    def fake_llm_call(**kwargs):
        llm_calls.append(kwargs)
        raise AssertionError("LLM must never be called on a cache hit")

    config = load_config()
    run_enrichment(
        conn,
        config,
        date(2026, 7, 19),
        fetch_grounding_fn=fake_fetch_grounding,
        content_hash_fn=fake_content_hash,
        llm_call_fn=fake_llm_call,
    )

    assert llm_calls == []


# --- ENR-05/D-08: grounding fetch failure -> LLM never called, no fabrication ---


def test_fetch_failure_skips_llm(db):
    from techtrend.config import load_config
    from techtrend.pipeline.enrich import run_enrichment

    conn = db
    entity_id = _insert_entity(conn, "1", full_name="owner/unreachable-repo")
    _insert_score(conn, entity_id, eligible=1)
    conn.commit()

    llm_calls = []

    def fake_fetch_grounding(full_name):
        return None, None  # both description and README unavailable

    def fake_llm_call(**kwargs):
        llm_calls.append(kwargs)
        raise AssertionError("LLM must never be called after a fetch failure")

    config = load_config()
    run_enrichment(
        conn,
        config,
        date(2026, 7, 19),
        fetch_grounding_fn=fake_fetch_grounding,
        llm_call_fn=fake_llm_call,
    )

    assert llm_calls == []
    row = conn.execute(
        "SELECT status, content_hash FROM enrichments WHERE entity_id = %s",
        (entity_id,),
    ).fetchone()
    assert row is not None
    assert row["status"] == "fetch_failed"
    assert row["content_hash"] is None


# --- ENR-06/D-10: one candidate's failure never aborts the run ---


def test_per_candidate_failure_does_not_abort_run(db):
    from techtrend.config import load_config
    from techtrend.pipeline.enrich import run_enrichment
    from techtrend.pipeline.llm import Confidence, EnrichmentResult

    conn = db
    failing = _insert_entity(conn, "1", full_name="owner/failing-repo")
    healthy = _insert_entity(conn, "2", full_name="owner/healthy-repo")
    _insert_score(conn, failing, wilson_lower_bound=0.9, eligible=1)
    _insert_score(conn, healthy, wilson_lower_bound=0.5, eligible=1)
    conn.commit()

    def fake_fetch_grounding(full_name):
        return full_name, full_name

    def fake_content_hash(description, readme_intro):
        return description  # distinct per candidate -- good enough as a fake hash

    def fake_llm_call(**kwargs):
        if kwargs["description"] == "owner/failing-repo":
            raise RuntimeError("simulated LLM failure")
        return EnrichmentResult(
            summary_line_1="what it is",
            summary_line_2="why it matters",
            section="agentic_coding_tools",
            confidence=Confidence.high,
        )

    config = load_config()
    written = run_enrichment(
        conn,
        config,
        date(2026, 7, 19),
        fetch_grounding_fn=fake_fetch_grounding,
        content_hash_fn=fake_content_hash,
        llm_call_fn=fake_llm_call,
    )

    # The failing candidate's error is isolated -- run_enrichment still
    # returns normally and still enriches the healthy candidate.
    assert written == 1
    failing_row = conn.execute(
        "SELECT status FROM enrichments WHERE entity_id = %s", (failing,)
    ).fetchone()
    assert failing_row is None
    healthy_row = conn.execute(
        "SELECT status FROM enrichments WHERE entity_id = %s", (healthy,)
    ).fetchone()
    assert healthy_row is not None
    assert healthy_row["status"] == "complete"


# --- TECHTREND_DISABLE_LLM: runtime kill-switch (quick task 260818-sbl) ---


def test_disable_llm_switch_skips_enrichment(db, monkeypatch):
    from unittest.mock import Mock

    import techtrend.enrich as enrich_mod

    conn = db
    monkeypatch.setenv("TECHTREND_DISABLE_LLM", "1")

    run_enrichment_mock = Mock()
    monkeypatch.setattr(enrich_mod, "run_enrichment", run_enrichment_mock)
    monkeypatch.setattr(enrich_mod, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(enrich_mod, "init_db", lambda *a, **k: None)
    # main() closes conn on the disabled path -- prevent it from closing the
    # shared `db` fixture connection out from under the fixture's own teardown.
    monkeypatch.setattr(conn, "close", lambda: None)

    exit_code = enrich_mod.main([])

    assert exit_code == 0
    run_enrichment_mock.assert_not_called()

    row = conn.execute(
        "SELECT status, item_count FROM run_manifest WHERE stage = 'enrich'"
    ).fetchone()
    assert row is not None
    assert row["status"] == "disabled"
    assert row["item_count"] == 0


@pytest.mark.parametrize(
    "value",
    ["1", "true", "TRUE", "yes", "on"],
)
def test_llm_disabled_truthy_values(value, monkeypatch):
    from techtrend.enrich import _llm_disabled

    monkeypatch.setenv("TECHTREND_DISABLE_LLM", value)
    assert _llm_disabled() is True


@pytest.mark.parametrize(
    "value",
    ["0", "false", "", "maybe"],
)
def test_llm_disabled_falsy_values(value, monkeypatch):
    from techtrend.enrich import _llm_disabled

    monkeypatch.setenv("TECHTREND_DISABLE_LLM", value)
    assert _llm_disabled() is False


def test_llm_disabled_unset(monkeypatch):
    from techtrend.enrich import _llm_disabled

    monkeypatch.delenv("TECHTREND_DISABLE_LLM", raising=False)
    assert _llm_disabled() is False


def test_disable_llm_switch_falsy_still_runs_enrichment(db, monkeypatch):
    from unittest.mock import Mock

    import techtrend.enrich as enrich_mod

    conn = db
    monkeypatch.setenv("TECHTREND_DISABLE_LLM", "0")

    run_enrichment_stub = Mock(return_value=0)
    monkeypatch.setattr(enrich_mod, "run_enrichment", run_enrichment_stub)
    monkeypatch.setattr(enrich_mod, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(enrich_mod, "init_db", lambda *a, **k: None)
    monkeypatch.setattr(conn, "close", lambda: None)

    exit_code = enrich_mod.main([])

    assert exit_code == 0
    run_enrichment_stub.assert_called_once()
