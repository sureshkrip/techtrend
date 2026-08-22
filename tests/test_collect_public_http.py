"""Tests for the unauthenticated public HTTP client + retry predicate
(D3-5 touch #3) -- techtrend.collectors.http.build_public_client and
is_retryable_public.

No test makes a live network call -- HTTP is driven through an
httpx.MockTransport, mirroring tests/test_collect_github.py's style.
"""

import httpx

from techtrend.collectors.http import build_public_client, is_retryable_public

# ---------------------------------------------------------------------------
# build_public_client (D3-5 touch #3, T-03-03)
# ---------------------------------------------------------------------------


def test_build_public_client_works_with_github_token_unset(monkeypatch):
    """The public client must be constructible and usable even when
    GITHUB_TOKEN is entirely absent from the environment -- it performs no
    token lookup at all, unlike build_client().
    """
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        resp = client.get("https://hn.algolia.com/api/v1/search")
    finally:
        client.close()

    resp.raise_for_status()
    assert resp.json() == {"ok": True}


def test_build_public_client_sends_no_authorization_header(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json={})

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        client.get("https://api.npmjs.org/downloads/point/last-week/some-pkg")
    finally:
        client.close()

    assert len(requests_seen) == 1
    headers = {k.lower() for k in requests_seen[0].headers.keys()}
    assert "authorization" not in headers


def test_build_public_client_sends_a_user_agent():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = build_public_client(transport=httpx.MockTransport(handler))
    try:
        resp = client.get("https://pypistats.org/api/packages/some-pkg/recent")
    finally:
        client.close()

    resp.raise_for_status()
    assert client.headers.get("user-agent")


# ---------------------------------------------------------------------------
# is_retryable_public (RESEARCH.md Pitfall 3, T-03-04)
# ---------------------------------------------------------------------------


def _status_error(status_code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://hn.algolia.com/api/v1/search")
    response = httpx.Response(status_code, headers=headers or {}, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_is_retryable_public_500_is_retried():
    assert is_retryable_public(_status_error(500)) is True


def test_is_retryable_public_429_is_retried():
    assert is_retryable_public(_status_error(429)) is True


def test_is_retryable_public_404_not_retried():
    assert is_retryable_public(_status_error(404)) is False


def test_is_retryable_public_403_not_retried():
    """Unlike GitHub's is_retryable, a 403 here is never retried -- these
    public APIs don't use GitHub's x-ratelimit-remaining:0 convention, so
    even a 403 carrying that header must NOT be treated as transient.
    """
    assert is_retryable_public(_status_error(403)) is False
    assert is_retryable_public(_status_error(403, {"x-ratelimit-remaining": "0"})) is False
