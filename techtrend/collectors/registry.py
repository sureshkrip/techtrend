"""The single file touched to add a source (COLL-06).

`COLLECTORS` is the list the orchestrator iterates. Nothing above this file
-- the orchestrator, identity resolution, snapshot writing -- may branch on
`source_id`; adding Phase 3's HN/npm/PyPI/RSS sources means writing a new
`techtrend/collectors/<source>.py` module implementing the `Collector`
protocol and appending one line here.
"""

from techtrend.collectors.base import Collector
from techtrend.collectors.github import GitHubCollector

COLLECTORS: list[Collector] = [GitHubCollector()]
