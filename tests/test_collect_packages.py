"""npm + PyPI download collector tests (COLL-04).

No test makes a live network call -- HTTP is driven through an
`httpx.MockTransport` seeded from the recorded fixtures under
`tests/fixtures/packages/`, mirroring `tests/test_collect_hn.py`.
"""

import json
from datetime import date
from pathlib import Path

import httpx

from techtrend.collectors.base import CollectedItem, Collector
from techtrend.collectors.http import build_public_client
from techtrend.collectors.packages import NpmCollector, PyPiCollector
from techtrend.config import Config, Packages

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "packages"


def _load_fixture(filename: str) -> dict:
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# NpmCollector.fetch -- one request per package, scoped-package %2F encoding
# ---------------------------------------------------------------------------


def test_npm_fetch_issues_one_request_per_package():
    npm_fixture = _load_fixture("npm_downloads.json")
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json=npm_fixture)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(packages=Packages(npm=["some-pkg", "another-pkg"], pypi=[]))
        results = NpmCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    assert len(seen_paths) == 2
    assert results[0]["package"] == "some-pkg"
    assert results[1]["package"] == "another-pkg"


def test_npm_fetch_scoped_package_encodes_slash_as_percent_2f():
    npm_fixture = _load_fixture("npm_downloads.json")
    seen_raw_paths: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_raw_paths.append(request.url.raw_path)
        return httpx.Response(200, json=npm_fixture)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(packages=Packages(npm=["@org/pkg"], pypi=[]))
        NpmCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    assert len(seen_raw_paths) == 1
    assert b"@org%2Fpkg" in seen_raw_paths[0]
    # The raw slash must not appear unescaped after the scope -- otherwise
    # npm's single-package endpoint would parse this as two path segments.
    assert b"@org/pkg" not in seen_raw_paths[0]


def test_npm_fetch_transport_error_skips_package_not_whole_run():
    """A transport-level failure on one package's request is logged and
    skipped rather than aborting the whole collect:npm stage -- mirrors
    HNCollector.fetch's per-keyword isolation.
    """
    npm_fixture = _load_fixture("npm_downloads.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if "doomed" in request.url.path:
            raise httpx.ConnectError("simulated connection reset", request=request)
        return httpx.Response(200, json=npm_fixture)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(packages=Packages(npm=["doomed-pkg", "healthy-pkg"], pypi=[]))
        results = NpmCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    assert len(results) == 1
    assert results[0]["package"] == "healthy-pkg"


def test_npm_fetch_with_no_packages_issues_no_requests():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request should be issued for an empty npm package list")

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(packages=Packages(npm=[], pypi=[]))
        results = NpmCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    assert results == []


# ---------------------------------------------------------------------------
# NpmCollector.normalize -- rolling last-week total into metrics["downloads"]
# ---------------------------------------------------------------------------


def test_npm_normalize_maps_downloads_into_metrics():
    npm_fixture = _load_fixture("npm_downloads.json")
    raw = dict(npm_fixture)
    raw["package"] = "some-pkg"

    item = NpmCollector().normalize(raw)

    assert isinstance(item, CollectedItem)
    assert item.source == "npm"
    assert item.source_native_id == "some-pkg"
    assert item.full_name == "some-pkg"
    assert item.url == "https://www.npmjs.com/package/some-pkg"
    # This IS the rolling last-week total (the endpoint queried is
    # downloads/point/last-week/...) -- pins that the fixture's raw
    # "downloads" value flows through unchanged.
    assert item.metrics["downloads"] == npm_fixture["downloads"]


def test_npm_normalize_missing_downloads_defaults_to_zero():
    raw = {"package": "some-pkg", "downloads": None}

    item = NpmCollector().normalize(raw)

    assert item.metrics["downloads"] == 0


# ---------------------------------------------------------------------------
# PyPiCollector.fetch -- one request per package
# ---------------------------------------------------------------------------


def test_pypi_fetch_issues_one_request_per_package():
    pypi_fixture = _load_fixture("pypi_recent.json")
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json=pypi_fixture)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(packages=Packages(npm=[], pypi=["some-pkg", "another-pkg"]))
        results = PyPiCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    assert len(seen_paths) == 2
    assert results[0]["package"] == "some-pkg"
    assert results[1]["package"] == "another-pkg"


def test_pypi_fetch_transport_error_skips_package_not_whole_run():
    pypi_fixture = _load_fixture("pypi_recent.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if "doomed" in request.url.path:
            raise httpx.ConnectError("simulated connection reset", request=request)
        return httpx.Response(200, json=pypi_fixture)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(packages=Packages(npm=[], pypi=["doomed-pkg", "healthy-pkg"]))
        results = PyPiCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    assert len(results) == 1
    assert results[0]["package"] == "healthy-pkg"


def test_pypi_fetch_with_no_packages_issues_no_requests():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request should be issued for an empty pypi package list")

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        config = Config(packages=Packages(npm=[], pypi=[]))
        results = PyPiCollector(config=config, client=client).fetch(since=date.today())
    finally:
        client.close()

    assert results == []


# ---------------------------------------------------------------------------
# PyPiCollector.normalize -- last_week (NOT last_day) into metrics["downloads"]
# ---------------------------------------------------------------------------


def test_pypi_normalize_maps_last_week_not_last_day_into_metrics():
    """Regression pin for RESEARCH.md Pitfall 1: the fixture's last_day
    (120) and last_week (3400) are deliberately distinct values so a
    regression to storing last_day fails this assertion.
    """
    pypi_fixture = _load_fixture("pypi_recent.json")
    raw = dict(pypi_fixture)
    raw["package"] = "some-pkg"

    item = PyPiCollector().normalize(raw)

    assert isinstance(item, CollectedItem)
    assert item.source == "pypi"
    assert item.source_native_id == "some-pkg"
    assert item.full_name == "some-pkg"
    assert item.url == "https://pypi.org/project/some-pkg/"
    assert item.metrics["downloads"] == pypi_fixture["data"]["last_week"]
    assert item.metrics["downloads"] != pypi_fixture["data"]["last_day"]


def test_pypi_normalize_missing_data_defaults_to_zero():
    raw = {"package": "some-pkg", "data": {}}

    item = PyPiCollector().normalize(raw)

    assert item.metrics["downloads"] == 0


# ---------------------------------------------------------------------------
# Collector protocol conformance (COLL-06)
# ---------------------------------------------------------------------------


def test_npm_collector_satisfies_collector_protocol():
    collector = NpmCollector()
    assert isinstance(collector, Collector)
    assert collector.source_id == "npm"
    assert callable(collector.fetch)
    assert callable(collector.normalize)


def test_pypi_collector_satisfies_collector_protocol():
    collector = PyPiCollector()
    assert isinstance(collector, Collector)
    assert collector.source_id == "pypi"
    assert callable(collector.fetch)
    assert callable(collector.normalize)
