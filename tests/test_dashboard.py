"""Dashboard route tests (DASH-01, DASH-03, DASH-04, DASH-05, DASH-06).

Every entity/scores/snapshots row is written directly against the shared
`db` fixture's ephemeral Postgres connection (CLAUDE.md testing philosophy:
no live network call, no live ingest/score run). `techtrend.server.app`'s
route calls `connect()` with no args, so the `pg_env` fixture repoints its
PG* env-var lookup at that same ephemeral database before each
`fastapi.testclient.TestClient` request, mirroring the pattern already
proven in `tests/test_skeleton.py`.
"""

import re

from fastapi.testclient import TestClient

import techtrend.config as config_module
from techtrend.db.connection import connect
from techtrend.pipeline.score import CURRENT_SCORE_VERSION

DEFAULT_WINDOW_DAYS = 7  # config/tracked.toml's Tunables.window_days default


def _insert_entity(
    conn,
    native_id,
    *,
    full_name=None,
    url=None,
    homepage=None,
    docs_url=None,
    docs_url_kind="repo",
):
    full_name = full_name or f"owner/{native_id}"
    url = url or f"https://github.com/{full_name}"
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, homepage, docs_url,
            docs_url_kind, discovery_method, admitted_at, last_seen_at
        ) VALUES (
            'github', %(native_id)s, %(full_name)s, %(url)s, %(homepage)s, %(docs_url)s,
            %(docs_url_kind)s, 'seed', '2026-07-01T00:00:00Z', '2026-07-19T00:00:00Z'
        )
        """,
        {
            "native_id": native_id,
            "full_name": full_name,
            "url": url,
            "homepage": homepage,
            "docs_url": docs_url,
            "docs_url_kind": docs_url_kind,
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
    score_version=CURRENT_SCORE_VERSION,
    stars_gained=100,
    window_days=DEFAULT_WINDOW_DAYS,
    wilson_lower_bound=0.5,
    eligible=1,
):
    conn.execute(
        """
        INSERT INTO scores (
            entity_id, run_date, score_version, stars_gained,
            window_days, wilson_lower_bound, eligible
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            entity_id,
            run_date,
            score_version,
            stars_gained,
            window_days,
            wilson_lower_bound,
            int(eligible),
        ),
    )


def _insert_snapshot(conn, entity_id, collected_at, value):
    conn.execute(
        """
        INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value, source_kind)
        VALUES (%s, %s, 'stars', %s, 'observed')
        """,
        (entity_id, collected_at, value),
    )


def _client():
    """Depends on the `pg_env` fixture already having pointed
    techtrend.db.connection.connect()'s zero-arg PG* env-var path at the
    ephemeral test database -- callers must also request `pg_env`.
    """
    from techtrend.server.app import app

    return TestClient(app)


def _sort_link_html(text, key):
    """Return the rendered `<a class="sort-link...">...</a>` block for the
    given sort key's column header, so a test can inspect whether
    `sort-active` and the glyph landed on that specific column.

    02-05: sort-header links now also carry `&section=...` (Pitfall #5, both
    controls must preserve each other's state) -- the regex tolerates that
    trailing query param rather than requiring an exact match on `sort=key`
    alone.
    """
    match = re.search(
        rf'<a class="sort-link( sort-active)?"\s+hx-get="/\?sort={key}(&section=[^"]*)?"[^>]*>.*?</a>',
        text,
        re.S,
    )
    assert match, f"sort link for sort={key} not found in response"
    return match.group(0)


# --- DASH-01: dense sortable table, ordering, adjacency, empty state ---


def test_ranked_rows_render_in_velocity_descending_order(db, pg_env):
    conn = db
    a = _insert_entity(conn, "1", full_name="owner/repo-a")
    b = _insert_entity(conn, "2", full_name="owner/repo-b")
    c = _insert_entity(conn, "3", full_name="owner/repo-c")
    _insert_score(conn, a, wilson_lower_bound=0.9)
    _insert_score(conn, b, wilson_lower_bound=0.5)
    _insert_score(conn, c, wilson_lower_bound=0.1)
    conn.commit()

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count('class="repo-name"') == 3
    assert (
        response.text.index("owner/repo-a")
        < response.text.index("owner/repo-b")
        < response.text.index("owner/repo-c")
    )


def test_equal_bounds_break_tie_by_entity_id_ascending_and_are_stable(db, pg_env):
    conn = db
    # Insert "zebra" first so it gets the lower entity id despite sorting
    # alphabetically after "alpha" -- proves the tiebreak is entities.id
    # ascending, not incidental insertion or name order.
    zebra = _insert_entity(conn, "1", full_name="owner/zebra")
    alpha = _insert_entity(conn, "2", full_name="owner/alpha")
    _insert_score(conn, zebra, wilson_lower_bound=0.5)
    _insert_score(conn, alpha, wilson_lower_bound=0.5)
    conn.commit()

    client = _client()
    first = client.get("/")
    second = client.get("/")

    assert first.status_code == 200
    assert first.text.index("owner/zebra") < first.text.index("owner/alpha")
    assert first.text == second.text


def test_zero_eligible_entities_renders_empty_state(db, pg_env):
    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert "No data yet" in response.text


# --- DASH-03: allow-listed sorting, boundary, ordering, precision ---


def test_sort_stars_reorders_and_unrecognized_sort_falls_back_to_velocity(db, pg_env):
    conn = db
    high_velocity_low_stars = _insert_entity(conn, "1", full_name="owner/fast-mover")
    low_velocity_high_stars = _insert_entity(conn, "2", full_name="owner/big-repo")
    _insert_score(conn, high_velocity_low_stars, wilson_lower_bound=0.9, stars_gained=50)
    _insert_score(conn, low_velocity_high_stars, wilson_lower_bound=0.1, stars_gained=30)
    _insert_snapshot(conn, high_velocity_low_stars, "2026-07-19", 10)
    _insert_snapshot(conn, low_velocity_high_stars, "2026-07-19", 1000)
    conn.commit()

    client = _client()

    default_response = client.get("/")
    assert default_response.status_code == 200
    assert default_response.text.index("owner/fast-mover") < default_response.text.index(
        "owner/big-repo"
    )

    stars_response = client.get("/?sort=stars")
    assert stars_response.status_code == 200
    assert stars_response.text.index("owner/big-repo") < stars_response.text.index(
        "owner/fast-mover"
    )

    fallback_response = client.get("/?sort=nonsense")
    assert fallback_response.status_code == 200
    assert fallback_response.text.index("owner/fast-mover") < fallback_response.text.index(
        "owner/big-repo"
    )


def test_hx_request_returns_only_the_table_partial(db, pg_env):
    conn = db
    entity_id = _insert_entity(conn, "1", full_name="owner/partial-only")
    _insert_score(conn, entity_id, wilson_lower_bound=0.5)
    conn.commit()

    client = _client()
    response = client.get("/?sort=stars", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "<html" not in response.text.lower()
    assert "owner/partial-only" in response.text


def test_active_sort_glyph_reflects_the_sort_actually_applied(db, pg_env):
    conn = db
    entity_id = _insert_entity(conn, "1", full_name="owner/glyph-check")
    _insert_score(conn, entity_id, wilson_lower_bound=0.5)
    conn.commit()

    client = _client()
    response = client.get("/?sort=nonsense")

    assert response.status_code == 200
    velocity_link = _sort_link_html(response.text, "velocity")
    stars_link = _sort_link_html(response.text, "stars")
    assert "sort-active" in velocity_link
    assert "sort-glyph" in velocity_link
    assert "sort-active" not in stars_link


def test_velocity_renders_four_decimals_while_sorting_on_unrounded_value(db, pg_env):
    conn = db
    # Both round to the same 4-decimal display ("0.5000") but differ at the
    # 6th decimal -- the unrounded value must still drive sort order.
    higher = _insert_entity(conn, "1", full_name="owner/six-hi")
    lower = _insert_entity(conn, "2", full_name="owner/six-lo")
    _insert_score(conn, higher, wilson_lower_bound=0.500009)
    _insert_score(conn, lower, wilson_lower_bound=0.500001)
    conn.commit()

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count("0.5000") == 2
    assert response.text.index("owner/six-hi") < response.text.index("owner/six-lo")


# --- DASH-04/DASH-05: honest outbound links ---


def test_row_links_source_before_docs_with_honest_label(db, pg_env):
    conn = db
    documented = _insert_entity(
        conn,
        "1",
        full_name="owner/documented-repo",
        url="https://github.com/owner/documented-repo",
        docs_url="https://docs.example.com/documented-repo",
        docs_url_kind="homepage",
    )
    undocumented = _insert_entity(
        conn,
        "2",
        full_name="owner/undocumented-repo",
        url="https://github.com/owner/undocumented-repo",
        docs_url=None,
        docs_url_kind="repo",
    )
    _insert_score(conn, documented, wilson_lower_bound=0.9)
    _insert_score(conn, undocumented, wilson_lower_bound=0.1)
    conn.commit()

    client = _client()
    response = client.get("/")
    text = response.text

    assert response.status_code == 200

    documented_row_start = text.index("owner/documented-repo")
    documented_row_end = text.index("</tr>", documented_row_start)
    documented_row = text[documented_row_start:documented_row_end]
    assert documented_row.index("View on GitHub") < documented_row.index(">Docs<")
    assert 'href="https://docs.example.com/documented-repo"' in documented_row

    undocumented_row_start = text.index("owner/undocumented-repo")
    undocumented_row_end = text.index("</tr>", undocumented_row_start)
    undocumented_row = text[undocumented_row_start:undocumented_row_end]
    assert undocumented_row.index("View on GitHub") < undocumented_row.index(">Repo<")
    # docs_url is None -- the docs anchor must fall back to the repo's own
    # URL rather than rendering an empty/None href, and it must never be
    # mislabeled "Docs" for a bare repo-URL fallback (D-15).
    assert undocumented_row.count('href="https://github.com/owner/undocumented-repo"') == 2
    assert ">Docs<" not in undocumented_row


# --- DASH-01/D-08a: partial-history footer note, singular/plural ---


def test_partial_history_footer_singular_for_one_excluded_entity(db, pg_env):
    conn = db
    ranked = _insert_entity(conn, "1", full_name="owner/ranked-repo")
    fresh = _insert_entity(conn, "2", full_name="owner/fresh-repo")
    _insert_score(conn, ranked, wilson_lower_bound=0.9, eligible=1, window_days=7)
    _insert_score(conn, fresh, eligible=0, window_days=1)
    conn.commit()

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert "1 repo is still building history and isn't ranked yet." in response.text


def test_partial_history_footer_plural_for_multiple_excluded_entities(db, pg_env):
    conn = db
    ranked = _insert_entity(conn, "1", full_name="owner/ranked-repo")
    fresh_a = _insert_entity(conn, "2", full_name="owner/fresh-repo-a")
    fresh_b = _insert_entity(conn, "3", full_name="owner/fresh-repo-b")
    _insert_score(conn, ranked, wilson_lower_bound=0.9, eligible=1, window_days=7)
    _insert_score(conn, fresh_a, eligible=0, window_days=1)
    _insert_score(conn, fresh_b, eligible=0, window_days=2)
    conn.commit()

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert (
        "2 repos are still building history and aren't ranked yet"
        " — check back after a few days of data collection." in response.text
    )


# --- Regression: score_version/eligible filter (defect carried from 01-04) ---


def test_ineligible_and_stale_score_version_rows_are_excluded(db, pg_env):
    conn = db
    current = _insert_entity(conn, "1", full_name="owner/current-eligible")
    ineligible = _insert_entity(conn, "2", full_name="owner/ineligible")
    stale_version = _insert_entity(conn, "3", full_name="owner/stale-version")
    _insert_score(conn, current, wilson_lower_bound=0.9, eligible=1)
    _insert_score(conn, ineligible, wilson_lower_bound=0.9, eligible=0)
    _insert_score(
        conn,
        stale_version,
        wilson_lower_bound=0.9,
        eligible=1,
        score_version=CURRENT_SCORE_VERSION - 1,
    )
    conn.commit()

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert "owner/current-eligible" in response.text
    assert "owner/ineligible" not in response.text
    assert "owner/stale-version" not in response.text


# --- Regression: run_date dedup (scores carries one row per run_date) ---


def test_entity_with_scores_across_two_run_dates_renders_exactly_once(db, pg_env):
    """`scores` is keyed on (entity_id, run_date, score_version) -- an entity
    that (for any reason) carries eligible rows at the same score_version
    across two different run_dates must still render as exactly one row,
    pinned to the most recent run_date, never once per run_date.
    """
    conn = db
    entity_id = _insert_entity(conn, "1", full_name="owner/multi-run-date")
    _insert_score(conn, entity_id, run_date="2026-07-17", wilson_lower_bound=0.3)
    _insert_score(conn, entity_id, run_date="2026-07-18", wilson_lower_bound=0.5)
    _insert_score(conn, entity_id, run_date="2026-07-19", wilson_lower_bound=0.7)
    conn.commit()

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    # Count rendered data rows, not raw substring occurrences of the full
    # name -- the name also appears inside the source/docs hrefs, so a
    # naive substring count would over-count even a single correct row.
    assert response.text.count('class="repo-name"') == 1
    # Pinned to the latest run_date's bound (0.7000), not an earlier one.
    assert "0.7000" in response.text


# --- V2/D-08a: three distinct empty states (no-run vs run-with-partial vs rows) ---


def test_no_successful_run_ever_renders_no_data_yet_state(db, pg_env):
    """State (a): a totally empty run_manifest (no collector run has ever
    succeeded) renders the 'No data yet / run ingest' copy -- distinct from
    state (b) below, which must never fall through to this branch.
    """
    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert "No data yet" in response.text
    assert "Still building history" not in response.text


def test_run_completed_but_nothing_eligible_renders_still_building_state(db, pg_env):
    """State (b): a run HAS completed successfully but every entity is
    still below the SCORE-03 floor (D-08a's expected first-week
    sparseness -- window_days=0/stars_gained=0 on day one). Must render the
    honest 'still building history' copy, never the false 'No run has
    completed yet' copy that the pre-fix code fell through to.
    """
    from techtrend.pipeline.orchestrator import record_stage

    conn = db
    record_stage(
        conn,
        "2026-07-19",
        "collect:github",
        "success",
        item_count=6,
        started_at="2026-07-19T09:00:00Z",
        finished_at="2026-07-19T09:00:05Z",
    )
    fresh_a = _insert_entity(conn, "1", full_name="owner/fresh-repo-a")
    fresh_b = _insert_entity(conn, "2", full_name="owner/fresh-repo-b")
    _insert_score(conn, fresh_a, eligible=0, window_days=0)
    _insert_score(conn, fresh_b, eligible=0, window_days=1)
    conn.commit()

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert "Still building history" in response.text
    assert "No data yet" not in response.text
    assert "No run has completed yet" not in response.text
    assert (
        "2 repos are still building history and aren't ranked yet"
        " — check back after a few days of data collection." in response.text
    )


# --- CR-03: config/DB failures degrade to honest copy, never a traceback ---


def test_malformed_toml_config_renders_db_error_not_traceback(db, pg_env, tmp_path, monkeypatch):
    bad_toml = tmp_path / "bad-tracked.toml"
    bad_toml.write_text("this is not valid toml [[[", encoding="utf-8")
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", bad_toml)

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    # Jinja2 autoescapes the apostrophe as &#39; -- match the copy without it.
    assert "read the database" in response.text
    assert "Traceback" not in response.text


def test_corrupt_db_file_renders_db_error_not_traceback(pg_env, monkeypatch):
    """There is no SQLite file to corrupt anymore -- storage is server-side
    Postgres. The equivalent failure mode is an unreachable/unreadable
    database: pointing PGDATABASE at a database that doesn't exist raises
    psycopg.OperationalError, the same exception class app.py's except
    clause degrades to DB_UNREADABLE_MESSAGE for.
    """
    monkeypatch.setenv("PGDATABASE", "techtrend_test_db_does_not_exist")

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert "read the database" in response.text
    assert "Traceback" not in response.text


def _insert_enrichment(
    conn,
    entity_id,
    *,
    content_hash="deadbeef",
    status="complete",
    summary_line_1="line 1",
    summary_line_2="line 2",
    section="agentic_coding_tools",
    confidence="high",
    low_confidence=0,
    computed_at="2026-07-19T00:00:00Z",
):
    conn.execute(
        """
        INSERT INTO enrichments (
            entity_id, content_hash, status, summary_line_1, summary_line_2,
            section, confidence, low_confidence, computed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            entity_id,
            content_hash,
            status,
            summary_line_1,
            summary_line_2,
            section,
            confidence,
            low_confidence,
            computed_at,
        ),
    )


# --- ENR-06: enrichment failure/cap-overflow never removes a ranked row ---


def test_unenriched_item_still_renders(db, pg_env):
    """An eligible entity with no `enrichments` row (cap overflow, fetch
    failure, or simply not enriched yet) must still appear in the ranked
    table -- D-10's 'summary pending' honest marker, never a dropped row."""
    conn = db
    entity_id = _insert_entity(conn, "1", full_name="owner/unenriched-repo")
    _insert_score(conn, entity_id, wilson_lower_bound=0.5, eligible=1)
    conn.commit()

    client = _client()
    response = client.get("/")

    assert response.status_code == 200
    assert "owner/unenriched-repo" in response.text
    assert "summary pending" in response.text


# --- DASH-02/D-13: ?section=X filters the ranked table ---


def test_section_filter(db, pg_env):
    """`?section=X` narrows the ranked table to that section's filings only
    (D-11/D-12); an unenriched item (no section yet) appears under the
    default 'All' view but drops out of every specific section filter
    (D-13)."""
    conn = db
    filed = _insert_entity(conn, "1", full_name="owner/filed-repo")
    unenriched = _insert_entity(conn, "2", full_name="owner/unenriched-repo")
    _insert_score(conn, filed, wilson_lower_bound=0.9, eligible=1)
    _insert_score(conn, unenriched, wilson_lower_bound=0.5, eligible=1)
    _insert_enrichment(conn, filed, section="agentic_coding_tools")
    conn.commit()

    client = _client()

    all_response = client.get("/")
    assert all_response.status_code == 200
    assert "owner/filed-repo" in all_response.text
    assert "owner/unenriched-repo" in all_response.text

    filtered_response = client.get("/?sort=velocity&section=agentic_coding_tools")
    assert filtered_response.status_code == 200
    assert "owner/filed-repo" in filtered_response.text
    assert "owner/unenriched-repo" not in filtered_response.text


def test_dashboard_never_writes_to_the_database(db, pg_env):
    conn = db
    entity_id = _insert_entity(conn, "1", full_name="owner/read-only-check")
    _insert_score(conn, entity_id, wilson_lower_bound=0.5)
    conn.commit()

    client = _client()

    def _counts():
        check = connect()
        result = {
            table: check.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in ("entities", "snapshots", "scores", "run_manifest")
        }
        check.close()
        return result

    before = _counts()
    response = client.get("/")
    after = client.get("/?sort=stars")
    final = _counts()

    assert response.status_code == 200
    assert after.status_code == 200
    assert before == final
