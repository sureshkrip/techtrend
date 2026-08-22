"""Hacker News collector tests (COLL-03).

No test makes a live network call -- HTTP is driven through an
`httpx.MockTransport` seeded from the recorded fixture under
`tests/fixtures/hn/`, mirroring `tests/test_collect_github.py`.
"""

import json
from datetime import date
from pathlib import Path

import httpx

from techtrend.collectors.base import CollectedItem, Collector
from techtrend.collectors.hn import HNCollector
from techtrend.collectors.http import build_public_client
from techtrend.config import Config, HackerNews

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "hn"


def _load_fixture(filename: str) -> dict:
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# fetch() -- one request per keyword, dedupe by objectID (COLL-03)
# ---------------------------------------------------------------------------


def test_fetch_issues_one_request_per_keyword_and_dedupes_by_object_id():
    search_fixture = _load_fixture("search_response.json")
    seen_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_queries.append(request.url.params.get("query", ""))
        assert request.url.params.get("tags") == "story"
        assert "numericFilters" in request.url.params
        return httpx.Response(200, json=search_fixture)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(hn=HackerNews(keywords=["ai agent", "llm coding"], lookback_days=7))
        results = HNCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    # One request per configured keyword, never OR'd/combined into one call.
    assert len(seen_queries) == 2
    assert seen_queries == ["ai agent", "llm coding"]
    # Both keyword passes returned the same fixture hits -- deduped by
    # objectID rather than multiplied by the number of keyword requests.
    assert len(results) == len(search_fixture["hits"])
    assert {r["objectID"] for r in results} == {h["objectID"] for h in search_fixture["hits"]}


def test_fetch_transport_error_skips_pass_not_whole_run():
    """A transport-level failure (connection reset, DNS blip, timeout) on one
    keyword's search pass is logged and skipped rather than aborting the
    whole collect:hn stage -- other keywords' hits still come through,
    mirroring GitHubCollector._discover's per-pass isolation.
    """
    search_fixture = _load_fixture("search_response.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("query") == "doomed":
            raise httpx.ConnectError("simulated connection reset", request=request)
        return httpx.Response(200, json=search_fixture)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(hn=HackerNews(keywords=["doomed", "healthy"], lookback_days=7))
        results = HNCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    # The healthy keyword's pass still contributed its hits; the run did not abort.
    assert len(results) == len(search_fixture["hits"])


def test_fetch_with_no_keywords_issues_no_requests():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request should be issued for an empty keyword list")

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(hn=HackerNews(keywords=[], lookback_days=7))
        results = HNCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    assert results == []


# ---------------------------------------------------------------------------
# normalize() -- points into metrics, self-post permalink fallback (COLL-03)
# ---------------------------------------------------------------------------


def test_normalize_maps_points_into_metrics():
    hit = _load_fixture("search_response.json")["hits"][0]
    item = HNCollector().normalize(hit)

    assert isinstance(item, CollectedItem)
    assert item.source == "hn"
    assert item.source_native_id == str(hit["objectID"])
    assert item.full_name == hit["title"]
    assert item.url == hit["url"]
    assert item.metrics["points"] == hit["points"]
    assert item.discovery_method == "hn-search"


def test_normalize_null_url_falls_back_to_hn_permalink():
    hits = _load_fixture("search_response.json")["hits"]
    self_post = next(h for h in hits if h.get("url") is None)

    item = HNCollector().normalize(self_post)

    assert item.url == f"https://news.ycombinator.com/item?id={self_post['objectID']}"


def test_normalize_missing_points_defaults_to_zero():
    hit = dict(_load_fixture("search_response.json")["hits"][0])
    hit["points"] = None

    item = HNCollector().normalize(hit)

    assert item.metrics["points"] == 0


# ---------------------------------------------------------------------------
# Collector protocol conformance (COLL-06)
# ---------------------------------------------------------------------------


def test_hn_collector_satisfies_collector_protocol():
    collector = HNCollector()
    assert isinstance(collector, Collector)
    assert collector.source_id == "hn"
    assert callable(collector.fetch)
    assert callable(collector.normalize)
