"""Dashboard route tests (DASH-01, DASH-03, DASH-04, DASH-05, DASH-06).

Every entity/scores/snapshots row is written directly against a real
temp-file SQLite connection (CLAUDE.md testing philosophy: no live network
call, no live ingest/score run). `techtrend.server.app`'s own DB dependency
is repointed at that same file via `monkeypatch` before each
`fastapi.testclient.TestClient` request, mirroring the pattern already
proven in `tests/test_skeleton.py`.
"""

import re

from fastapi.testclient import TestClient

import techtrend.db.connection as connection_module
from techtrend.db.connection import connect, init_db
from techtrend.pipeline.score import CURRENT_SCORE_VERSION
from techtrend.server.app import app

DEFAULT_WINDOW_DAYS = 7  # config/tracked.toml's Tunables.window_days default


def _seed_db(tmp_path, name="dash-test.db"):
    """Return (db_path, conn) for an initialized temp-file DB, open for writes."""
    db_path = tmp_path / name
    conn = connect(db_path)
    init_db(conn)
    return db_path, conn


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
            'github', :native_id, :full_name, :url, :homepage, :docs_url,
            :docs_url_kind, 'seed', '2026-07-01T00:00:00Z', '2026-07-19T00:00:00Z'
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
        "SELECT id FROM entities WHERE source = 'github' AND source_native_id = ?",
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
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
        VALUES (?, ?, 'stars', ?, 'observed')
        """,
        (entity_id, collected_at, value),
    )


def _client(monkeypatch, db_path):
    """Point the app's DB dependency at db_path and return a fresh TestClient."""
    monkeypatch.setattr(connection_module, "DEFAULT_DB_PATH", db_path)
    return TestClient(app)


def _sort_link_html(text, key):
    """Return the rendered `<a class="sort-link...">...</a>` block for the
    given sort key's column header, so a test can inspect whether
    `sort-active` and the glyph landed on that specific column.
    """
    match = re.search(
        rf'<a class="sort-link( sort-active)?"\s+hx-get="/\?sort={key}"[^>]*>.*?</a>',
        text,
        re.S,
    )
    assert match, f"sort link for sort={key} not found in response"
    return match.group(0)


# --- DASH-01: dense sortable table, ordering, adjacency, empty state ---


def test_ranked_rows_render_in_velocity_descending_order(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    a = _insert_entity(conn, "1", full_name="owner/repo-a")
    b = _insert_entity(conn, "2", full_name="owner/repo-b")
    c = _insert_entity(conn, "3", full_name="owner/repo-c")
    _insert_score(conn, a, wilson_lower_bound=0.9)
    _insert_score(conn, b, wilson_lower_bound=0.5)
    _insert_score(conn, c, wilson_lower_bound=0.1)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count('class="repo-name"') == 3
    assert (
        response.text.index("owner/repo-a")
        < response.text.index("owner/repo-b")
        < response.text.index("owner/repo-c")
    )


def test_equal_bounds_break_tie_by_entity_id_ascending_and_are_stable(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    # Insert "zebra" first so it gets the lower entity id despite sorting
    # alphabetically after "alpha" -- proves the tiebreak is entities.id
    # ascending, not incidental insertion or name order.
    zebra = _insert_entity(conn, "1", full_name="owner/zebra")
    alpha = _insert_entity(conn, "2", full_name="owner/alpha")
    _insert_score(conn, zebra, wilson_lower_bound=0.5)
    _insert_score(conn, alpha, wilson_lower_bound=0.5)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)
    first = client.get("/")
    second = client.get("/")

    assert first.status_code == 200
    assert first.text.index("owner/zebra") < first.text.index("owner/alpha")
    assert first.text == second.text


def test_zero_eligible_entities_renders_empty_state(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/")

    assert response.status_code == 200
    assert "No data yet" in response.text


# --- DASH-03: allow-listed sorting, boundary, ordering, precision ---


def test_sort_stars_reorders_and_unrecognized_sort_falls_back_to_velocity(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    high_velocity_low_stars = _insert_entity(conn, "1", full_name="owner/fast-mover")
    low_velocity_high_stars = _insert_entity(conn, "2", full_name="owner/big-repo")
    _insert_score(conn, high_velocity_low_stars, wilson_lower_bound=0.9, stars_gained=50)
    _insert_score(conn, low_velocity_high_stars, wilson_lower_bound=0.1, stars_gained=30)
    _insert_snapshot(conn, high_velocity_low_stars, "2026-07-19", 10)
    _insert_snapshot(conn, low_velocity_high_stars, "2026-07-19", 1000)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)

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


def test_hx_request_returns_only_the_table_partial(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    entity_id = _insert_entity(conn, "1", full_name="owner/partial-only")
    _insert_score(conn, entity_id, wilson_lower_bound=0.5)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/?sort=stars", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "<html" not in response.text.lower()
    assert "owner/partial-only" in response.text


def test_active_sort_glyph_reflects_the_sort_actually_applied(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    entity_id = _insert_entity(conn, "1", full_name="owner/glyph-check")
    _insert_score(conn, entity_id, wilson_lower_bound=0.5)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/?sort=nonsense")

    assert response.status_code == 200
    velocity_link = _sort_link_html(response.text, "velocity")
    stars_link = _sort_link_html(response.text, "stars")
    assert "sort-active" in velocity_link
    assert "sort-glyph" in velocity_link
    assert "sort-active" not in stars_link


def test_velocity_renders_four_decimals_while_sorting_on_unrounded_value(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    # Both round to the same 4-decimal display ("0.5000") but differ at the
    # 6th decimal -- the unrounded value must still drive sort order.
    higher = _insert_entity(conn, "1", full_name="owner/six-hi")
    lower = _insert_entity(conn, "2", full_name="owner/six-lo")
    _insert_score(conn, higher, wilson_lower_bound=0.500009)
    _insert_score(conn, lower, wilson_lower_bound=0.500001)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count("0.5000") == 2
    assert response.text.index("owner/six-hi") < response.text.index("owner/six-lo")


# --- DASH-04/DASH-05: honest outbound links ---


def test_row_links_source_before_docs_with_honest_label(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
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
    conn.close()

    client = _client(monkeypatch, db_path)
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


def test_partial_history_footer_singular_for_one_excluded_entity(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    ranked = _insert_entity(conn, "1", full_name="owner/ranked-repo")
    fresh = _insert_entity(conn, "2", full_name="owner/fresh-repo")
    _insert_score(conn, ranked, wilson_lower_bound=0.9, eligible=1, window_days=7)
    _insert_score(conn, fresh, eligible=0, window_days=1)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/")

    assert response.status_code == 200
    assert "1 repo is still building history and isn't ranked yet." in response.text


def test_partial_history_footer_plural_for_multiple_excluded_entities(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    ranked = _insert_entity(conn, "1", full_name="owner/ranked-repo")
    fresh_a = _insert_entity(conn, "2", full_name="owner/fresh-repo-a")
    fresh_b = _insert_entity(conn, "3", full_name="owner/fresh-repo-b")
    _insert_score(conn, ranked, wilson_lower_bound=0.9, eligible=1, window_days=7)
    _insert_score(conn, fresh_a, eligible=0, window_days=1)
    _insert_score(conn, fresh_b, eligible=0, window_days=2)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/")

    assert response.status_code == 200
    assert (
        "2 repos are still building history and aren't ranked yet"
        " — check back after a few days of data collection." in response.text
    )


# --- Regression: score_version/eligible filter (defect carried from 01-04) ---


def test_ineligible_and_stale_score_version_rows_are_excluded(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
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
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/")

    assert response.status_code == 200
    assert "owner/current-eligible" in response.text
    assert "owner/ineligible" not in response.text
    assert "owner/stale-version" not in response.text


# --- Regression: run_date dedup (scores carries one row per run_date) ---


def test_entity_with_scores_across_two_run_dates_renders_exactly_once(tmp_path, monkeypatch):
    """`scores` is keyed on (entity_id, run_date, score_version) -- an entity
    that (for any reason) carries eligible rows at the same score_version
    across two different run_dates must still render as exactly one row,
    pinned to the most recent run_date, never once per run_date.
    """
    db_path, conn = _seed_db(tmp_path)
    entity_id = _insert_entity(conn, "1", full_name="owner/multi-run-date")
    _insert_score(conn, entity_id, run_date="2026-07-17", wilson_lower_bound=0.3)
    _insert_score(conn, entity_id, run_date="2026-07-18", wilson_lower_bound=0.5)
    _insert_score(conn, entity_id, run_date="2026-07-19", wilson_lower_bound=0.7)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)
    response = client.get("/")

    assert response.status_code == 200
    # Count rendered data rows, not raw substring occurrences of the full
    # name -- the name also appears inside the source/docs hrefs, so a
    # naive substring count would over-count even a single correct row.
    assert response.text.count('class="repo-name"') == 1
    # Pinned to the latest run_date's bound (0.7000), not an earlier one.
    assert "0.7000" in response.text


def test_dashboard_never_writes_to_the_database(tmp_path, monkeypatch):
    db_path, conn = _seed_db(tmp_path)
    entity_id = _insert_entity(conn, "1", full_name="owner/read-only-check")
    _insert_score(conn, entity_id, wilson_lower_bound=0.5)
    conn.commit()
    conn.close()

    client = _client(monkeypatch, db_path)

    def _counts():
        check = connect(db_path)
        result = {
            table: check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
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
