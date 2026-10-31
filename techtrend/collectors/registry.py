"""The single file touched to add a source (COLL-06).

`COLLECTORS` is the list the orchestrator iterates. Nothing above this file
-- the orchestrator, identity resolution, snapshot writing -- may branch on
`source_id`; adding Phase 3's HN/npm/PyPI/RSS sources means writing a new
`techtrend/collectors/<source>.py` module implementing the `Collector`
protocol and appending one line here.

Phase 3 (COLL-03/COLL-04/COLL-05) adds four sources: HN, npm, PyPI, and
vendor changelogs. Each collector's construction stays side-effect-free
(config/client resolved lazily inside fetch()), so building this list at
import time never touches the network, the filesystem config, or requires
GITHUB_TOKEN.
"""

from techtrend.collectors.base import Collector
from techtrend.collectors.changelog import ChangelogCollector
from techtrend.collectors.github import GitHubCollector
from techtrend.collectors.hn import HNCollector
from techtrend.collectors.huggingface import HuggingFaceCollector
from techtrend.collectors.lobsters import LobstersCollector
from techtrend.collectors.packages import NpmCollector, PyPiCollector
from techtrend.collectors.reddit import RedditCollector

COLLECTORS: list[Collector] = [
    GitHubCollector(),
    HNCollector(),
    NpmCollector(),
    PyPiCollector(),
    ChangelogCollector(),
    HuggingFaceCollector(),
    LobstersCollector(),
    RedditCollector(),
]
