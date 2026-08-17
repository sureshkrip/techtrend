-- TechTrend storage schema.
-- Five tables: entities, snapshots, scores, run_manifest, enrichments.
-- Every CREATE uses IF NOT EXISTS so init_db() is safely re-runnable.

CREATE TABLE IF NOT EXISTS entities (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL,                    -- 'github'
    source_native_id TEXT NOT NULL,          -- GitHub repo numeric id (stable across renames)
    full_name TEXT NOT NULL,                 -- 'owner/repo'
    url TEXT NOT NULL,
    homepage TEXT,
    docs_url TEXT,
    docs_url_kind TEXT,                      -- 'homepage' | 'readme' | 'repo'  (D-15)
    discovery_method TEXT NOT NULL,          -- 'seed' | 'search' | 'force-include'
    admitted_at TEXT NOT NULL,               -- ISO8601
    last_seen_at TEXT NOT NULL,
    dormant_at TEXT,                         -- D-02
    backfilled_at TEXT,                      -- D-08
    backfill_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'complete'|'blocked'|'failed'
    force_excluded INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source, source_native_id)
);

CREATE TABLE IF NOT EXISTS snapshots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entities(id),
    collected_at TEXT NOT NULL,              -- ISO8601 date, day granularity
    metric_name TEXT NOT NULL,               -- 'stars' | 'releases'
    metric_value BIGINT NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'observed',  -- 'observed' | 'backfill'  (D-07)
    UNIQUE(entity_id, collected_at, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_entity_date ON snapshots(entity_id, collected_at);

CREATE TABLE IF NOT EXISTS scores (
    entity_id BIGINT NOT NULL REFERENCES entities(id),
    run_date TEXT NOT NULL,
    score_version INTEGER NOT NULL,
    stars_gained BIGINT NOT NULL,
    window_days INTEGER NOT NULL,            -- may be <7 for a fresh entity
    wilson_lower_bound DOUBLE PRECISION NOT NULL,
    eligible INTEGER NOT NULL,               -- 0/1 -- cleared SCORE-03 floor
    PRIMARY KEY (entity_id, run_date, score_version)
);

CREATE TABLE IF NOT EXISTS run_manifest (
    run_date TEXT NOT NULL,
    stage TEXT NOT NULL,                     -- 'collect:github' | 'backfill:github' | 'score' | 'enrich'
    status TEXT NOT NULL,                    -- 'success' | 'failed' | 'zero_items'
    item_count INTEGER,
    error_detail TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    PRIMARY KEY (run_date, stage)
);

CREATE TABLE IF NOT EXISTS enrichments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entities(id),
    content_hash TEXT,                 -- NULL only when status='fetch_failed' (D-08, D-10)
    status TEXT NOT NULL,               -- 'complete' | 'fetch_failed' (D-08)
    summary_line_1 TEXT,                -- "what this is" (D-01, ENR-03)
    summary_line_2 TEXT,                -- "why it matters" (D-01, ENR-03)
    section TEXT,                       -- one of the seven config-driven ids (D-02, ENR-04)
    confidence TEXT,                    -- 'high' | 'medium' | 'low' (D-02, Common Pitfall 2)
    low_confidence INTEGER NOT NULL DEFAULT 0,  -- precomputed vs confidence_flag_threshold (D-02)
    computed_at TEXT NOT NULL,          -- ISO8601, drives the MAX(computed_at) "current row" join (D-09)
    UNIQUE(entity_id, content_hash)     -- composite cache key (D-09); Postgres treats each NULL
                                         -- as distinct, so multiple fetch_failed tombstones per
                                         -- entity across runs are allowed
);
CREATE INDEX IF NOT EXISTS idx_enrichments_entity_computed
    ON enrichments(entity_id, computed_at);
