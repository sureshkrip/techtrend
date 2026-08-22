"""Vendor changelog collector tests (COLL-05).

No test makes a live network call -- `feedparser.parse()` is pointed at the
local fixture file under `tests/fixtures/changelog/`, which feedparser reads
directly from disk with no HTTP involved, mirroring the fixture-backed
pattern in `tests/test_collect_hn.py` / `tests/test_collect_packages.py`.

Window-boundary assertions inject a fixed `now` (rather than relying on
`datetime.now(UTC)` at test-run time) so the fixture's hardcoded entry dates
stay deterministic forever instead of drifting out of window as wall-clock
time passes.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import feedparser

from techtrend.collectors.base import CollectedItem, Collector
from techtrend.collectors.changelog import ChangelogCollector, count_entries_in_window
from techtrend.config import ChangelogFeed, Config

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "changelog"
SAMPLE_FEED_PATH = FIXTURES_DIR / "sample_feed.xml"

# Fixed reference point the fixture's four entries are dated relative to:
# 2026-01-14 (1 day before), 2026-01-10 (5 days before), 2026-01-05
# (10 days before), 2025-12-01 (45 days before).
FIXED_NOW = datetime(2026, 1, 15, tzinfo=UTC)


# ---------------------------------------------------------------------------
# count_entries_in_window -- in-window counting + narrow-window boundary case
# ---------------------------------------------------------------------------


def test_count_entries_in_window_counts_only_entries_within_lookback():
    parsed = feedparser.parse(str(SAMPLE_FEED_PATH))

    # 7-day lookback from FIXED_NOW (cutoff 2026-01-08) includes the two
    # newest entries (01-14, 01-10) and excludes the two older ones
    # (01-05, 2025-12-01).
    count = count_entries_in_window(parsed, lookback_days=7, now=FIXED_NOW)

    assert count == 2


def test_count_entries_in_window_narrow_lookback_excludes_older_entries():
    """Boundary case: a window narrower than the entries' spread counts
    only the in-window subset -- narrowing from 7 to 2 days drops the
    01-10 entry, leaving only 01-14.
    """
    parsed = feedparser.parse(str(SAMPLE_FEED_PATH))

    count = count_entries_in_window(parsed, lookback_days=2, now=FIXED_NOW)

    assert count == 1


# ---------------------------------------------------------------------------
# fetch() -- local-file feed parsing, no network, per-feed failure isolation
# ---------------------------------------------------------------------------


def test_fetch_parses_local_fixture_feed_and_counts_in_window_releases():
    config = Config(
        changelogs=[ChangelogFeed(label="ExampleVendor", url=str(SAMPLE_FEED_PATH))]
    )
    collector = ChangelogCollector(config=config, lookback_days=7, now=FIXED_NOW)

    results = collector.fetch(since=date.today())

    assert len(results) == 1
    assert results[0]["label"] == "ExampleVendor"
    assert results[0]["url"] == str(SAMPLE_FEED_PATH)
    assert results[0]["releases_count"] == 2


def test_fetch_skips_dead_feed_not_whole_run():
    """A feed that fails to parse (bad path -> feedparser sets `bozo`) is
    logged and skipped rather than aborting the whole collector run --
    mirrors GitHubCollector._discover / HNCollector.fetch's per-item
    isolation.
    """
    dead_path = FIXTURES_DIR / "does-not-exist.xml"
    config = Config(
        changelogs=[
            ChangelogFeed(label="DeadFeed", url=str(dead_path)),
            ChangelogFeed(label="ExampleVendor", url=str(SAMPLE_FEED_PATH)),
        ]
    )
    collector = ChangelogCollector(config=config, lookback_days=7, now=FIXED_NOW)

    results = collector.fetch(since=date.today())

    # The healthy feed's pass still contributed; the dead feed contributed
    # nothing but did not abort the run.
    assert len(results) == 1
    assert results[0]["label"] == "ExampleVendor"


def test_fetch_with_no_changelogs_issues_no_results():
    config = Config(changelogs=[])
    collector = ChangelogCollector(config=config)

    results = collector.fetch(since=date.today())

    assert results == []


# ---------------------------------------------------------------------------
# normalize() -- releases count into metrics, label as source_native_id
# ---------------------------------------------------------------------------


def test_normalize_maps_release_count_into_metrics():
    raw = {"label": "ExampleVendor", "url": str(SAMPLE_FEED_PATH), "releases_count": 2}

    item = ChangelogCollector().normalize(raw)

    assert isinstance(item, CollectedItem)
    assert item.source == "changelog"
    assert item.source_native_id == "ExampleVendor"
    assert item.full_name == "ExampleVendor"
    assert item.url == str(SAMPLE_FEED_PATH)
    assert item.metrics["releases"] == 2
    assert item.discovery_method == "changelog-feed"


# ---------------------------------------------------------------------------
# Collector protocol conformance (COLL-06)
# ---------------------------------------------------------------------------


def test_changelog_collector_satisfies_collector_protocol():
    collector = ChangelogCollector()
    assert isinstance(collector, Collector)
    assert collector.source_id == "changelog"
    assert callable(collector.fetch)
    assert callable(collector.normalize)
