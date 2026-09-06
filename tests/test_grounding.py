"""Grounding text extraction/normalization/fetch tests (D-07, D-08, D-09,
ENR-05, Common Pitfall 1 -- badge-churn cache defeat; 02-VALIDATION.md
Wave 0 + 02-03 Task 2 fetch_grounding contract; quick task 260906-n5d
source-aware dispatcher).

`extract_intro`/`normalize_for_hash` were Wave 0 failing scaffolds; the
`fetch_grounding` tests below were added in Plan 02-03 (Task 2) since Wave 0
did not scaffold them -- same RED-before-implementation discipline, driven
through an `httpx.MockTransport` (no live GitHub call), mirroring
`tests/test_collect_github.py`'s style.

Quick task 260906-n5d made `fetch_grounding` source-dispatching (github/hn/
npm/pypi/changelog) so non-GitHub entities stop 404ing against the GitHub
REST API and silently vanishing from enrichment. The GitHub tests below now
call through the new dispatcher signature; a `github_client`/`public_client`
kwarg pair replaces the old single positional `client`.
"""

import json
from pathlib import Path

import httpx

from techtrend.collectors.http import build_client, build_public_client

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "github"
PACKAGES_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "packages"
CHANGELOG_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "changelog"
SAMPLE_FEED_PATH = CHANGELOG_FIXTURES_DIR / "sample_feed.xml"


def _load_readme_with_badges() -> str:
    return (FIXTURES_DIR / "readme_with_badges.md").read_text(encoding="utf-8")


def _load_packages_fixture(filename: str) -> dict:
    return json.loads((PACKAGES_FIXTURES_DIR / filename).read_text(encoding="utf-8"))


def test_extract_intro_truncates_at_first_deep_heading():
    from techtrend.pipeline.grounding import extract_intro

    readme_text = _load_readme_with_badges()
    intro = extract_intro(readme_text, char_cap=2000)

    assert "Example Badge Repo" in intro
    assert "## Installation" not in intro
    assert "Install with your package manager" not in intro


def test_extract_intro_respects_char_cap():
    from techtrend.pipeline.grounding import extract_intro

    readme_text = _load_readme_with_badges()
    intro = extract_intro(readme_text, char_cap=20)

    assert len(intro) <= 20


def test_normalize_for_hash_strips_badges_and_comments_and_collapses_whitespace():
    from techtrend.pipeline.grounding import extract_intro, normalize_for_hash

    readme_text = _load_readme_with_badges()
    intro = extract_intro(readme_text, char_cap=2000)
    normalized = normalize_for_hash("A short repo description.", intro)

    assert "![" not in normalized
    assert "<!--" not in normalized
    assert "  " not in normalized  # no run of two+ spaces after collapsing


def test_normalize_for_hash_is_stable_across_badge_only_changes():
    """Pitfall 1: a badge/CI-status flip must never register as a content
    change -- otherwise the (entity, content_hash) cache almost never hits
    for actively-CI'd repos and DATA-04/SC4's cost guarantee breaks."""
    from techtrend.pipeline.grounding import normalize_for_hash

    intro_a = "Intro text.\n\n![build](https://img.shields.io/badge/build-passing)"
    intro_b = "Intro text.\n\n![build](https://img.shields.io/badge/build-failing)"

    assert normalize_for_hash("desc", intro_a) == normalize_for_hash("desc", intro_b)


# ---------------------------------------------------------------------------
# fetch_grounding dispatcher -- source="github" preserves the original
# behavior byte-for-byte through the new dispatch layer (ENR-05, D-08).
# ---------------------------------------------------------------------------


def test_fetch_grounding_github_returns_description_and_intro_on_success(
    monkeypatch, tmp_path, github_fixture
):
    from techtrend.pipeline.grounding import fetch_grounding

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    metadata = github_fixture("repo_metadata.json")
    readme_text = _load_readme_with_badges()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            return httpx.Response(200, text=readme_text)
        return httpx.Response(200, json=metadata)

    client = build_client(
        transport=httpx.MockTransport(handler), cache_db_path=tmp_path / "hishel.db"
    )
    try:
        result = fetch_grounding(
            "github",
            metadata["full_name"],
            "https://github.com/" + metadata["full_name"],
            2000,
            github_client=client,
            public_client=None,
        )
    finally:
        client.close()

    assert result is not None
    description, intro = result
    assert description == metadata["description"]
    assert "Example Badge Repo" in intro
    assert "## Installation" not in intro


def test_fetch_grounding_github_returns_none_when_description_and_readme_both_empty(
    monkeypatch, tmp_path, github_fixture
):
    """ENR-05/D-08: description empty AND README unfetchable/empty -> None,
    the signal for the caller to skip the LLM entirely rather than fabricate."""
    from techtrend.pipeline.grounding import fetch_grounding

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    metadata = dict(github_fixture("repo_metadata.json"))
    metadata["description"] = None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json=metadata)

    client = build_client(
        transport=httpx.MockTransport(handler), cache_db_path=tmp_path / "hishel.db"
    )
    try:
        result = fetch_grounding(
            "github",
            metadata["full_name"],
            "https://github.com/" + metadata["full_name"],
            2000,
            github_client=client,
            public_client=None,
        )
    finally:
        client.close()

    assert result is None


# ---------------------------------------------------------------------------
# hn -- grounds on the already-stored story title, no network fetch (D-08)
# ---------------------------------------------------------------------------


def test_fetch_hn_grounding_returns_title_as_description_with_empty_body():
    from techtrend.pipeline.grounding import _fetch_hn_grounding

    result = _fetch_hn_grounding("Show HN: A New AI Coding Tool", 2000)

    assert result is not None
    description, body = result
    assert description == "Show HN: A New AI Coding Tool"
    assert body == ""


def test_fetch_hn_grounding_empty_title_returns_none():
    from techtrend.pipeline.grounding import _fetch_hn_grounding

    assert _fetch_hn_grounding("   ", 2000) is None
    assert _fetch_hn_grounding("", 2000) is None


def test_fetch_grounding_dispatches_hn_source():
    from techtrend.pipeline.grounding import fetch_grounding

    result = fetch_grounding(
        "hn", "Show HN: A New AI Coding Tool", "https://news.ycombinator.com/item?id=1",
        2000, github_client=None, public_client=None,
    )

    assert result == ("Show HN: A New AI Coding Tool", "")


# ---------------------------------------------------------------------------
# npm -- fetches the first-party packument via the unauthenticated public
# client; scoped packages URL-encode the slash as %2F (D-08).
# ---------------------------------------------------------------------------


def test_fetch_npm_grounding_returns_description_and_readme_intro():
    from techtrend.pipeline.grounding import _fetch_npm_grounding

    packument = _load_packages_fixture("npm_registry.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=packument)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        result = _fetch_npm_grounding(client, "some-pkg", 2000)
    finally:
        client.close()

    assert result is not None
    description, intro = result
    assert description == packument["description"]
    assert "some-pkg" in intro
    assert "## Installation" not in intro


def test_fetch_npm_grounding_scoped_package_encodes_slash_as_percent_2f():
    from techtrend.pipeline.grounding import _fetch_npm_grounding

    packument = _load_packages_fixture("npm_registry.json")
    seen_raw_paths: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_raw_paths.append(request.url.raw_path)
        return httpx.Response(200, json=packument)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        _fetch_npm_grounding(client, "@org/pkg", 2000)
    finally:
        client.close()

    assert len(seen_raw_paths) == 1
    assert b"@org%2Fpkg" in seen_raw_paths[0]
    assert b"@org/pkg" not in seen_raw_paths[0]


def test_fetch_npm_grounding_404_returns_none():
    from techtrend.pipeline.grounding import _fetch_npm_grounding

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Not found"})

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        result = _fetch_npm_grounding(client, "does-not-exist-pkg", 2000)
    finally:
        client.close()

    assert result is None


def test_fetch_npm_grounding_both_empty_returns_none():
    from techtrend.pipeline.grounding import _fetch_npm_grounding

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"description": "", "readme": ""})

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        result = _fetch_npm_grounding(client, "empty-pkg", 2000)
    finally:
        client.close()

    assert result is None


def test_fetch_grounding_dispatches_npm_source():
    from techtrend.pipeline.grounding import fetch_grounding

    packument = _load_packages_fixture("npm_registry.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=packument)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        result = fetch_grounding(
            "npm", "some-pkg", "https://www.npmjs.com/package/some-pkg", 2000,
            github_client=None, public_client=client,
        )
    finally:
        client.close()

    assert result is not None
    assert result[0] == packument["description"]


# ---------------------------------------------------------------------------
# pypi -- fetches pypi.org's JSON API (distinct from pypistats), summary +
# description intro (D-08).
# ---------------------------------------------------------------------------


def test_fetch_pypi_grounding_returns_summary_and_description_intro():
    from techtrend.pipeline.grounding import _fetch_pypi_grounding

    metadata = _load_packages_fixture("pypi_metadata.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=metadata)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        result = _fetch_pypi_grounding(client, "some-pkg", 2000)
    finally:
        client.close()

    assert result is not None
    description, intro = result
    assert description == metadata["info"]["summary"]
    assert "some-pkg" in intro
    assert "## Installation" not in intro


def test_fetch_pypi_grounding_404_returns_none():
    from techtrend.pipeline.grounding import _fetch_pypi_grounding

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        result = _fetch_pypi_grounding(client, "does-not-exist-pkg", 2000)
    finally:
        client.close()

    assert result is None


def test_fetch_pypi_grounding_both_empty_returns_none():
    from techtrend.pipeline.grounding import _fetch_pypi_grounding

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"info": {"summary": "", "description": ""}})

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        result = _fetch_pypi_grounding(client, "empty-pkg", 2000)
    finally:
        client.close()

    assert result is None


def test_fetch_grounding_dispatches_pypi_source():
    from techtrend.pipeline.grounding import fetch_grounding

    metadata = _load_packages_fixture("pypi_metadata.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=metadata)

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        result = fetch_grounding(
            "pypi", "some-pkg", "https://pypi.org/project/some-pkg/", 2000,
            github_client=None, public_client=client,
        )
    finally:
        client.close()

    assert result is not None
    assert result[0] == metadata["info"]["summary"]


# ---------------------------------------------------------------------------
# changelog -- re-parses the feed fresh (not a collector) and grounds on
# real in-feed content: feed title + recent entry titles (D-08).
# ---------------------------------------------------------------------------


def test_fetch_changelog_grounding_returns_feed_title_and_entry_titles():
    from techtrend.pipeline.grounding import _fetch_changelog_grounding

    result = _fetch_changelog_grounding("ExampleVendor", str(SAMPLE_FEED_PATH), 2000)

    assert result is not None
    description, body = result
    assert description == "Sample Vendor Changelog"
    assert "Release v1.4.0" in body


def test_fetch_changelog_grounding_bozo_or_empty_feed_returns_none():
    from techtrend.pipeline.grounding import _fetch_changelog_grounding

    dead_path = CHANGELOG_FIXTURES_DIR / "does-not-exist.xml"

    assert _fetch_changelog_grounding("DeadFeed", str(dead_path), 2000) is None


def test_fetch_grounding_dispatches_changelog_source():
    from techtrend.pipeline.grounding import fetch_grounding

    result = fetch_grounding(
        "changelog", "ExampleVendor", str(SAMPLE_FEED_PATH), 2000,
        github_client=None, public_client=None,
    )

    assert result is not None
    assert result[0] == "Sample Vendor Changelog"


# ---------------------------------------------------------------------------
# unknown source -- dispatcher never raises, honest tombstone (D-08)
# ---------------------------------------------------------------------------


def test_fetch_grounding_unknown_source_returns_none():
    from techtrend.pipeline.grounding import fetch_grounding

    result = fetch_grounding(
        "carrier-pigeon", "whatever", "https://example.com", 2000,
        github_client=None, public_client=None,
    )

    assert result is None
