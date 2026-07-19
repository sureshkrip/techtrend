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
    """
    native_id = (item.source_native_id or "").strip()
    if not native_id:
        logger.warning(
            "stage=identity source=%s full_name=%s note=rejected empty source_native_id",
            item.source,
            item.full_name,
        )
        return None

    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO entities (
            source, source_native_id, full_name, url, homepage,
            discovery_method, admitted_at, last_seen_at
        ) VALUES (
            :source, :native_id, :full_name, :url, :homepage,
            :discovery_method, :now, :now
        )
        ON CONFLICT(source, source_native_id) DO UPDATE SET
            full_name = excluded.full_name,
            url = excluded.url,
            homepage = excluded.homepage,
            last_seen_at = excluded.last_seen_at
        """,
        {
            "source": item.source,
            "native_id": native_id,
            "full_name": item.full_name,
            "url": item.url,
            "homepage": item.homepage,
            "discovery_method": item.discovery_method,
            "now": now_iso,
        },
    )
    row = conn.execute(
        "SELECT id FROM entities WHERE source = ? AND source_native_id = ?",
        (item.source, native_id),
    ).fetchone()
    return row["id"]
