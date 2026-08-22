"""Vendor changelog collector (COLL-05).

`ChangelogCollector` is the third of three independent Wave 2 source modules
-- this module and its tests are the whole deliverable; registry wiring for
all four new collectors is Wave 3's job (see 03-CONTEXT.md D3-1), performed
in this same plan (03-06) because 03-04/03-05 deliberately left `registry.py`
untouched to keep the parallel collector plans conflict-free.

Parses curated Atom/RSS feed URLs (D3-4, `config.changelogs` -- each entry
carries a `label` + `url`) via `feedparser`. A changelog "release" is an
event, not a cumulative count (D3-3): this collector counts feed entries
whose `published_parsed`/`updated_parsed` timestamp falls within the
trailing lookback window and reports that count as `metrics={"releases": N}`
-- the same (gain, total) shape every other source produces, so it rides
the existing velocity model through `normalize.ChangelogMomentum` (identity
pass-through) with no scorer change.

`feedparser` normalizes both RSS 2.0 (`published`) and Atom (`updated`)
fields into the same `*_parsed` `time.struct_time` attribute on each entry
(RESEARCH.md), so no RSS-vs-Atom branching is needed here.
"""

import logging
from datetime import UTC, date, datetime, timedelta

import feedparser

from techtrend.collectors.base import CollectedItem
from techtrend.config import Config, load_config

logger = logging.getLogger(__name__)

# Trailing window (days) for counting feed entries as "in window" (D3-3).
# Matches the scorer's own default trailing window (config.tunables.window_days)
# so a changelog release counted here lines up with the same period the
# velocity model scores every other source over.
DEFAULT_LOOKBACK_DAYS = 7


def count_entries_in_window(
    parsed: feedparser.FeedParserDict,
    lookback_days: int,
    *,
    now: datetime | None = None,
) -> int:
    """Count `parsed.entries` whose publish/update timestamp falls within
    the trailing `lookback_days` window from `now` (defaults to the real
    current time in production; tests inject a fixed `now` so the window
    boundary against a static fixture file stays deterministic forever,
    rather than drifting as wall-clock time passes).

    An entry carrying neither `published_parsed` nor `updated_parsed` is
    skipped rather than counted -- there is no timestamp to judge it
    in-window by, and silently including it would inflate the release count
    with undated noise.
    """
    reference = now or datetime.now(UTC)
    cutoff = reference - timedelta(days=lookback_days)
    count = 0
    for entry in parsed.entries:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published is None:
            continue
        entry_dt = datetime(*published[:6], tzinfo=UTC)
        if entry_dt >= cutoff:
            count += 1
    return count


class ChangelogCollector:
    """Parses curated changelog feeds via feedparser. `source_id = "changelog"`."""

    source_id = "changelog"

    def __init__(
        self,
        config: Config | None = None,
        lookback_days: int | None = None,
        now: datetime | None = None,
    ):
        # config resolved lazily inside fetch(), matching every other
        # collector's shape -- construction stays side-effect-free so
        # registry.py can build `ChangelogCollector()` at import time.
        # No client is threaded through here (unlike GitHubCollector/
        # HNCollector/NpmCollector/PyPiCollector): feedparser.parse() takes
        # a URL or local path directly and manages its own I/O, so there is
        # no httpx.Client seam for it to share. `now` is an optional
        # injection seam (mirrors `transport`/`cache_db_path` elsewhere in
        # this codebase) so tests can pin the window cutoff against a
        # static fixture file deterministically -- production callers omit
        # it and get the real current time.
        self._config = config
        self._lookback_days = lookback_days
        self._now = now

    def fetch(self, since: date) -> list[dict]:
        """Parse every configured changelog feed, returning one raw dict per
        feed carrying {label, url, releases_count}.

        A feed that fails to parse (`parsed.bozo` set) or whose fetch raises
        is logged and skipped rather than aborting the whole collector run
        -- one dead feed must not lose every other feed's releases, mirroring
        GitHubCollector._discover's per-pass isolation.
        """
        config = self._config or load_config()
        lookback_days = self._lookback_days or DEFAULT_LOOKBACK_DAYS
        results = []
        for feed in config.changelogs:
            try:
                parsed = feedparser.parse(feed.url)
            except Exception as exc:  # feedparser itself does not raise on
                # malformed feeds (it sets `bozo` instead), but a network/IO
                # failure passed straight through to urllib can still raise.
                logger.warning(
                    "stage=collect:changelog feed=%s error=%s note=feed skipped",
                    feed.label,
                    exc,
                )
                continue
            if getattr(parsed, "bozo", False):
                logger.warning(
                    "stage=collect:changelog feed=%s error=%s note=feed skipped (bozo)",
                    feed.label,
                    getattr(parsed, "bozo_exception", "malformed feed"),
                )
                continue
            releases_count = count_entries_in_window(parsed, lookback_days, now=self._now)
            results.append(
                {
                    "label": feed.label,
                    "url": feed.url,
                    "releases_count": releases_count,
                }
            )
        return results

    def normalize(self, raw: dict) -> CollectedItem:
        """Map one `fetch()` result onto the source-agnostic CollectedItem.

        `source_native_id` is the feed's curated label (there is no
        per-entry vendor id to derive it from otherwise -- Claude's
        Discretion, CONTEXT.md). `metrics={"releases": N}` matches
        `normalize.PRIMARY_METRIC['changelog']` and rides the existing
        velocity model via `normalize.ChangelogMomentum` (identity
        pass-through, D3-3).
        """
        return CollectedItem(
            source=self.source_id,
            source_native_id=raw["label"],
            full_name=raw["label"],
            url=raw["url"],
            metrics={"releases": raw["releases_count"]},
            discovery_method="changelog-feed",
        )
