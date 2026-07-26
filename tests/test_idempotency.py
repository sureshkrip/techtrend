"""Identity resolution, snapshot writing, and full-collection idempotency.

Covers DATA-01 (adjacency/empty/ordering) and COLL-09 (adjacency/empty/
ordering) at the `resolve_entity`/`write_snapshot` level, plus DATA-05
(re-running a full collection does not duplicate rows) at the
`run_collection` orchestrator level.
"""

from datetime import UTC, date, datetime

from techtrend.collectors.base import CollectedItem
from techtrend.pipeline.identity import resolve_entity
from techtrend.pipeline.orchestrator import run_collection
from techtrend.pipeline.snapshot import write_snapshot

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


def _item(**overrides) -> CollectedItem:
    defaults = dict(
        source="github",
        source_native_id="741883704",
        full_name="Aider-AI/aider",
        url="https://github.com/Aider-AI/aider",
        homepage="https://aider.chat",
        description="aider is AI pair programming in your terminal",
        metrics={"stars": 34521},
        topics=["ai", "llm"],
        discovery_method="seed",
    )
    defaults.update(overrides)
    return CollectedItem(**defaults)


class _FakeCollector:
    """A minimal `Collector` for orchestrator-level tests -- `fetch` replays
    a fixed list of raw dicts, `normalize` maps them through a caller-supplied
    function, so tests never depend on live GitHub or a network call.
    """

    def __init__(self, source_id, raw_items, normalize_fn, fetch_error=None):
        self.source_id = source_id
        self._raw_items = raw_items
        self._normalize_fn = normalize_fn
        self._fetch_error = fetch_error

    def fetch(self, since):  # noqa: ARG002 - since unused by the fake
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._raw_items

    def normalize(self, raw):
        return self._normalize_fn(raw)


# ---------------------------------------------------------------------------
# resolve_entity: DATA-01 / COLL-09 adjacency, empty, ordering
# ---------------------------------------------------------------------------


def test_resolve_entity_same_identity_key_yields_one_entities_row(db):
    resolve_entity(db, _item(), NOW)
    resolve_entity(db, _item(), NOW)
    db.commit()

    count = db.execute(
        "SELECT COUNT(*) FROM entities WHERE source = 'github' AND source_native_id = '741883704'"
    ).fetchone()[0]
    assert count == 1


def test_resolve_entity_renamed_repo_same_native_id_updates_existing_row(db):
    resolve_entity(db, _item(full_name="Aider-AI/aider"), NOW)
    resolve_entity(db, _item(full_name="Aider-AI/aider-renamed"), NOW)
    db.commit()

    rows = db.execute(
        "SELECT full_name FROM entities WHERE source = 'github' AND source_native_id = '741883704'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Aider-AI/aider-renamed"


def test_resolve_entity_null_source_native_id_rejected_without_error(db):
    result = resolve_entity(db, _item(source_native_id=None), NOW)
    db.commit()

    assert result is None
    assert db.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0


def test_resolve_entity_empty_source_native_id_rejected_without_error(db):
    result = resolve_entity(db, _item(source_native_id="  "), NOW)
    db.commit()

    assert result is None
    assert db.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0


def test_resolve_entity_order_independent(db, tmp_path):
    """Resolving the same item set in reversed order produces an identical
    entities table by (source, source_native_id, full_name).
    """
    from techtrend.db.connection import connect, init_db

    items = [
        _item(source_native_id="1", full_name="a/one"),
        _item(source_native_id="2", full_name="b/two"),
        _item(source_native_id="3", full_name="c/three"),
    ]

    for item in items:
        resolve_entity(db, item, NOW)
    db.commit()

    reversed_db = connect(tmp_path / "reversed.db")
    init_db(reversed_db)
    for item in reversed(items):
        resolve_entity(reversed_db, item, NOW)
    reversed_db.commit()

    forward_rows = sorted(
        (r["source"], r["source_native_id"], r["full_name"])
        for r in db.execute("SELECT source, source_native_id, full_name FROM entities")
    )
    reversed_rows = sorted(
        (r["source"], r["source_native_id"], r["full_name"])
        for r in reversed_db.execute("SELECT source, source_native_id, full_name FROM entities")
    )
    reversed_db.close()

    assert forward_rows == reversed_rows


# ---------------------------------------------------------------------------
# write_snapshot: append-only upsert
# ---------------------------------------------------------------------------


def test_write_snapshot_upsert_replaces_same_day_value(db):
    entity_id = resolve_entity(db, _item(), NOW)
    db.commit()

    write_snapshot(db, entity_id, "2026-07-19", "stars", 100)
    write_snapshot(db, entity_id, "2026-07-19", "stars", 150)
    db.commit()

    rows = db.execute(
        "SELECT metric_value FROM snapshots WHERE entity_id = ? AND collected_at = '2026-07-19'"
        " AND metric_name = 'stars'",
        (entity_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["metric_value"] == 150


def test_write_snapshot_upsert_also_updates_source_kind_on_conflict(db):
    """WR-02 regression: a later write for the same
    (entity_id, collected_at, metric_name) under a different source_kind
    must update the stored provenance label too, not just metric_value --
    otherwise `source_kind` can end up describing where the value used to
    come from rather than where the currently-stored value came from
    (D-07's auditability guarantee).
    """
    entity_id = resolve_entity(db, _item(), NOW)
    db.commit()

    write_snapshot(db, entity_id, "2026-07-19", "stars", 100, source_kind="backfill")
    write_snapshot(db, entity_id, "2026-07-19", "stars", 150, source_kind="observed")
    db.commit()

    row = db.execute(
        "SELECT metric_value, source_kind FROM snapshots"
        " WHERE entity_id = ? AND collected_at = '2026-07-19' AND metric_name = 'stars'",
        (entity_id,),
    ).fetchone()
    assert row["metric_value"] == 150
    assert row["source_kind"] == "observed"

    # And the reverse direction: an 'observed' row overwritten by a later
    # 'backfill' write also picks up the new label -- the policy is
    # "whichever write happened most recently wins", not a one-way ratchet.
    write_snapshot(db, entity_id, "2026-07-19", "stars", 200, source_kind="backfill")
    db.commit()

    row = db.execute(
        "SELECT metric_value, source_kind FROM snapshots"
        " WHERE entity_id = ? AND collected_at = '2026-07-19' AND metric_name = 'stars'",
        (entity_id,),
    ).fetchone()
    assert row["metric_value"] == 200
    assert row["source_kind"] == "backfill"


# ---------------------------------------------------------------------------
# run_collection: DATA-01 empty, DATA-05 full-run idempotency
# ---------------------------------------------------------------------------


def test_run_collection_empty_item_list_creates_zero_entities_but_writes_run_manifest(db):
    fake = _FakeCollector("empty-source", [], lambda raw: _item())
    run_collection(db, date(2026, 7, 19), [fake])

    assert db.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0
    manifest_rows = db.execute(
        "SELECT * FROM run_manifest WHERE stage = 'collect:empty-source'"
    ).fetchall()
    assert len(manifest_rows) == 1


def test_run_collection_twice_same_fixture_same_run_date_is_idempotent(db, github_fixture):
    metadata = github_fixture("repo_metadata.json")

    def normalize(raw):
        return CollectedItem(
            source="github",
            source_native_id=str(raw["id"]),
            full_name=raw["full_name"],
            url=raw["html_url"],
            homepage=raw.get("homepage"),
            metrics={"stars": raw["stargazers_count"], "releases": 3},
            discovery_method="seed",
        )

    fake = _FakeCollector("github", [metadata], normalize)
    run_date = date(2026, 7, 19)

    run_collection(db, run_date, [fake])
    run_collection(db, run_date, [fake])

    assert db.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2  # stars + releases
