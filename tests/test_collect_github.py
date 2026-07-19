"""GitHub collector tests (COLL-01, COLL-02, COLL-06, COLL-07, COLL-08, COLL-09).

No test makes a live network call -- HTTP is driven through an
`httpx.MockTransport` seeded from the recorded fixtures under
`tests/fixtures/github/`, per `.claude/CLAUDE.md`'s testing philosophy.
"""

import httpx

from techtrend.collectors.base import CollectedItem, Collector
from techtrend.collectors.github import GitHubCollector, admit_repo
from techtrend.collectors.http import build_client, is_retryable
from techtrend.collectors.registry import COLLECTORS

# ---------------------------------------------------------------------------
# admit_repo (D-01/D-03/D-04)
# ---------------------------------------------------------------------------

_ADMIT_KWARGS = {
    "seed": {"seed-org/seed-repo"},
    "topics_allowlist": {"llm", "ai-agents"},
    "keywords": ["ai agent", "retrieval augmented"],
    "force_include": {"pinned-org/pinned-repo"},
    "force_exclude": {"banned-org/banned-repo"},
}


def test_admit_repo_seed_list_repo_admitted():
    assert admit_repo("seed-org/seed-repo", **_ADMIT_KWARGS) is True


def test_admit_repo_allowlisted_topic_admitted():
    assert (
        admit_repo(
            "someorg/new-repo",
            topics=["llm", "unrelated"],
            **_ADMIT_KWARGS,
        )
        is True
    )


def test_admit_repo_untagged_keyword_match_admitted():
    assert (
        admit_repo(
            "someorg/brand-new-agent-runner",
            topics=[],
            description="A lightweight ai agent runner for orchestrating LLM tool calls",
            **_ADMIT_KWARGS,
        )
        is True
    )


def test_admit_repo_force_included_admitted():
    assert admit_repo("pinned-org/pinned-repo", **_ADMIT_KWARGS) is True


def test_admit_repo_force_excluded_wins_over_topic_match():
    assert (
        admit_repo(
            "banned-org/banned-repo",
            topics=["llm"],
            **_ADMIT_KWARGS,
        )
        is False
    )


# ---------------------------------------------------------------------------
# is_retryable (COLL-07 boundary)
# ---------------------------------------------------------------------------


def _status_error(status_code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.github.com/repos/a/b")
    response = httpx.Response(status_code, headers=headers or {}, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_is_retryable_500_is_retried():
    assert is_retryable(_status_error(500)) is True


def test_is_retryable_403_ratelimit_exhausted_is_retried():
    assert is_retryable(_status_error(403, {"x-ratelimit-remaining": "0"})) is True


def test_is_retryable_403_permission_denied_not_retried():
    assert is_retryable(_status_error(403)) is False


def test_is_retryable_404_not_retried():
    assert is_retryable(_status_error(404)) is False


# ---------------------------------------------------------------------------
# Conditional (ETag) requests (COLL-08 boundary)
# ---------------------------------------------------------------------------


def test_repo_metadata_replayed_twice_issues_conditional_request_and_304_is_cache_hit(
    monkeypatch, tmp_path, github_fixture
):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    metadata = github_fixture("repo_metadata.json")
    etag = '"fixture-etag"'
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"etag": etag})
        return httpx.Response(
            200,
            json=metadata,
            headers={"etag": etag, "cache-control": "private, no-cache"},
        )

    client = build_client(
        transport=httpx.MockTransport(handler),
        cache_db_path=tmp_path / "hishel.db",
    )
    try:
        first = client.get("https://api.github.com/repos/Aider-AI/aider")
        second = client.get("https://api.github.com/repos/Aider-AI/aider")
    finally:
        client.close()

    # The collector-facing response is always a clean 200 -- a 304 is
    # resolved transparently by the cache layer, never surfaced as an error.
    first.raise_for_status()
    second.raise_for_status()
    assert first.status_code == 200
    assert second.status_code == 200

    # Two real network round-trips happened; the second carried the ETag
    # from the first as a conditional If-None-Match header.
    assert len(requests_seen) == 2
    assert requests_seen[1].headers.get("if-none-match") == etag


# ---------------------------------------------------------------------------
# normalize (COLL-09)
# ---------------------------------------------------------------------------


def test_normalize_maps_metadata_fixture_onto_collected_item(github_fixture):
    metadata = github_fixture("repo_metadata.json")
    collector = GitHubCollector()

    item = collector.normalize(
        {"metadata": metadata, "release_count": 12, "readme_text": None, "discovery_method": "seed"}
    )

    assert isinstance(item, CollectedItem)
    assert item.source == "github"
    # source_native_id is the numeric GitHub id as a string -- never full_name.
    assert item.source_native_id == str(metadata["id"])
    assert item.source_native_id != metadata["full_name"]
    assert item.full_name == metadata["full_name"]
    assert item.metrics["stars"] == metadata["stargazers_count"]
    assert item.metrics["releases"] == 12


# ---------------------------------------------------------------------------
# Registry (COLL-06)
# ---------------------------------------------------------------------------


def test_collectors_registry_has_exactly_one_entry_satisfying_protocol():
    assert len(COLLECTORS) == 1
    for collector in COLLECTORS:
        assert isinstance(collector, Collector)
        assert isinstance(collector.source_id, str)
        assert callable(collector.fetch)
        assert callable(collector.normalize)
    assert COLLECTORS[0].source_id == "github"
