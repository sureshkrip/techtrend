"""Match-or-create entity resolution (COLL-09).

Entities key strictly on `(source, source_native_id)` -- no cross-source
resolution in v1 (ARCHITECTURE.md "Deliberate simplification"). The identity
key is guarded first: an item with a null/empty `source_native_id` is
rejected before it ever reaches SQL, because an empty identity key would
silently collide with every other such entity under the same upsert target.
"""

import logging
from datetime import datetime

from techtrend.collectors.base import CollectedItem
from techtrend.pipeline.docs_link import resolve_docs_url

logger = logging.getLogger(__name__)


def resolve_entity(conn, item: CollectedItem, now: datetime) -> int | None:
    """Match-or-create the entities row for `item`. Returns the entity id, or
    `None` if `item.source_native_id` is null/empty -- callers must count
    that as a rejection rather than treating `None` as an error.

    Upsert is keyed on `(source, source_native_id)` (COLL-09): a repo whose
    `full_name` changed but whose native id is unchanged updates the
    existing row rather than creating a second entity. `admitted_at` is set
    only on insert and is never touched on conflict -- first-admission time
    is history, not a running "last touched" timestamp.

    Also resolves and writes `docs_url`/`docs_url_kind` via `resolve_docs_url`
    (DASH-05, D-15) on every call, insert or update, so a repo that later
    gains a homepage gets an improved link on the next run.
    """
    native_id = (item.source_native_id or "").strip()
    if not native_id:
        logger.warning(
            "stage=identity source=%s full_name=%s note=rejected empty source_native_id",
            item.source,
            item.full_name,
        )
        return None

    docs_url, docs_url_kind = resolve_docs_url(
        {"homepage": item.homepage, "html_url": item.url},
        item.readme_text,
    )

    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, homepage,
            docs_url, docs_url_kind, discovery_method, admitted_at, last_seen_at
        ) VALUES (
            %(source)s, %(native_id)s, %(full_name)s, %(url)s, %(homepage)s,
            %(docs_url)s, %(docs_url_kind)s, %(discovery_method)s, %(now)s, %(now)s
        )
        ON CONFLICT(source, source_native_id) DO UPDATE SET
            full_name = excluded.full_name,
            url = excluded.url,
            homepage = excluded.homepage,
            docs_url = excluded.docs_url,
            docs_url_kind = excluded.docs_url_kind,
            last_seen_at = excluded.last_seen_at
        """,
        {
            "source": item.source,
            "native_id": native_id,
            "full_name": item.full_name,
            "url": item.url,
            "homepage": item.homepage,
            "docs_url": docs_url,
            "docs_url_kind": docs_url_kind,
            "discovery_method": item.discovery_method,
            "now": now_iso,
        },
    )
    row = conn.execute(
        "SELECT id FROM entities WHERE source = %s AND source_native_id = %s",
        (item.source, native_id),
    ).fetchone()
    return row["id"]
