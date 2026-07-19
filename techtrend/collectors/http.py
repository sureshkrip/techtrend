"""Shared HTTP client: hishel RFC 9111 caching + the tenacity retry predicate.

`GITHUB_TOKEN` is read ONLY in this module -- never re-declared, logged, or
passed through `techtrend/collectors/github.py` (T-01-12 mitigation; enforced
by the plan's acceptance-criteria grep confining the literal `GITHUB_TOKEN`
to this file).

hishel constructor shape (RESEARCH.md Assumption A3 was unverified against
the installed version -- confirmed against hishel 1.3.0, which is installed):
`hishel.httpx.SyncCacheTransport(next_transport, storage, policy)` wraps a
raw `httpx.BaseTransport`. `hishel.SyncSqliteStorage(database_path=...)` is
the persistent storage backend.

`CacheOptions(shared=False)` is deliberate, not the hishel default
(`shared=True`): a shared cache models a proxy/CDN serving multiple users and
RFC 9111 forbids it from storing a `Cache-Control: private` response --
exactly what GitHub's authenticated API responses carry. This is a private,
single-user desktop cache, so `shared=False` is the correct policy, not a
tuning knob.
"""

import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from hishel import CacheOptions, SpecificationPolicy, SyncSqliteStorage
from hishel.httpx import SyncCacheTransport

logger = logging.getLogger(__name__)

HISHEL_CACHE_DIR = Path(".hishel")
HISHEL_CACHE_DB = HISHEL_CACHE_DIR / "github.db"

load_dotenv()


class MissingGithubTokenError(RuntimeError):
    """Raised at startup when GITHUB_TOKEN is absent from the environment/.env.

    Never silently falls back to the 60 req/hr unauthenticated budget --
    that failure mode is invisible until the run mysteriously starts getting
    rate-limited.
    """


def _default_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise MissingGithubTokenError(
            "GITHUB_TOKEN is not set. Copy .env.example to .env and add a "
            "fine-grained personal access token with public-repo read access."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "techtrend/0.1 (contact: sureshkrip@gmail.com)",
    }


def build_client(
    *,
    transport: httpx.BaseTransport | None = None,
    cache_db_path: Path | None = None,
) -> httpx.Client:
    """Return an httpx.Client wrapping a hishel cache and carrying GitHub auth headers.

    `transport` lets tests inject an `httpx.MockTransport` beneath the cache
    layer so no test makes a live network call; production callers omit it
    and get a real `httpx.HTTPTransport`.

    `cache_db_path` lets tests point the hishel storage at a tmp_path so
    repeated test runs never share cache state with the real `.hishel/`
    directory (which would make conditional-request tests order-dependent
    on whatever ETag a prior run happened to cache).
    """
    resolved_db = cache_db_path or HISHEL_CACHE_DB
    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    storage = SyncSqliteStorage(database_path=str(resolved_db))
    policy = SpecificationPolicy(cache_options=CacheOptions(shared=False))
    cache_transport = SyncCacheTransport(
        next_transport=transport or httpx.HTTPTransport(),
        storage=storage,
        policy=policy,
    )
    return httpx.Client(transport=cache_transport, headers=_default_headers(), timeout=30.0)


def is_retryable(exc: BaseException) -> bool:
    """COLL-07 retry predicate, fed to `tenacity.retry_if_exception` in github.py.

    5xx and a 403 carrying `x-ratelimit-remaining: 0` are transient -- back
    off and retry. A 403 *without* that header (permission-denied) and a 404
    are permanent; those belong to the caller, never to a retry loop.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        if resp.status_code >= 500:
            return True
        if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
            return True
    return False
