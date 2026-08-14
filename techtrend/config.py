"""Load and validate the non-secret tracked-repo config (config/tracked.toml).

Every tunable named in config/tracked.toml must be read through this module —
application code never re-declares one of these numbers as a literal
(CONTEXT.md "Claude's Discretion": config, not code constant).
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

from techtrend import paths

# Env-overridable via TECHTREND_CONFIG. Unlike DB/cache/logs this does NOT follow
# TECHTREND_DATA_DIR — tracked.toml is image-baked config, not runtime state.
DEFAULT_CONFIG_PATH = paths.CONFIG_PATH


class Seed(BaseModel):
    repos: list[str] = Field(default_factory=list)


class Discovery(BaseModel):
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class Overrides(BaseModel):
    force_include: list[str] = Field(default_factory=list)
    force_exclude: list[str] = Field(default_factory=list)


class Tunables(BaseModel):
    # 7-day trailing window for velocity computation (D-09).
    window_days: int = 7
    # SCORE-03 absolute floor on stars gained within the window (D-10).
    window_gain_floor: int = 25
    # Days of no meaningful star movement before a repo is marked dormant (D-02).
    dormancy_days: int = 90
    # Hard per-repo cap on stargazer-pagination requests during backfill (D-06).
    backfill_request_cap: int = 20
    # Days of historical star accrual to reconstruct during backfill, trimmed
    # from the newest sampled point backwards (D-06, ~90 days).
    backfill_lookback_days: int = 90
    # Health header strip escalates when last successful run exceeds this age (D-16).
    staleness_hours: int = 36
    # Size of the top-N set for the day-to-day Jaccard rank-overlap stability metric (D-12).
    stability_top_n: int = 25
    # Trailing runs averaged for the D-16 zero-items floor check.
    zero_items_trailing_runs: int = 5
    # Hard per-run cap on enrichment LLM calls, independent of ranking
    # threshold (ENR-02, D-04). Applied to the candidate SET (which entities
    # are even fetched), not just successful LLM calls -- see A6.
    enrichment_cap: int = 15
    # README intro truncation cap in characters, before the first H2+ heading
    # (D-07).
    grounding_char_cap: int = 2000
    # Claude model id for the summarize+classify call (D-03).
    enrichment_model: str = "claude-haiku-4-5"
    # Confidence tier that trips the low-confidence dashboard flag (D-02);
    # enum-only ("high"|"medium"|"low") -- JSON Schema has no numeric range
    # support, see Common Pitfall 2.
    confidence_flag_threshold: str = "low"


class SectionDef(BaseModel):
    # One of the seven fixed v1 taxonomy entries (ENR-04, D-15, A4). id is
    # the stable filing key stored in enrichments.section; label/description
    # are shown in the dashboard sidebar and fed into the LLM prompt's
    # section-definitions block.
    id: str
    label: str
    description: str


class Config(BaseModel):
    seed: Seed = Field(default_factory=Seed)
    discovery: Discovery = Field(default_factory=Discovery)
    overrides: Overrides = Field(default_factory=Overrides)
    tunables: Tunables = Field(default_factory=Tunables)
    # Seven-section taxonomy (ENR-04, D-15, A4), declared order preserved --
    # the LLM section enum is built from this order, not re-sorted.
    sections: list[SectionDef] = Field(default_factory=list)


def load_config(path: Path | None = None) -> Config:
    """Read config/tracked.toml (or the given path) and return a validated Config.

    Every Tunables field carries a default so a partial config file still validates.
    """
    resolved = path if path is not None else DEFAULT_CONFIG_PATH
    with open(resolved, "rb") as f:
        raw = tomllib.load(f)
    return Config.model_validate(raw)
