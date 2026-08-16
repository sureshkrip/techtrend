"""Daily pipeline entry point: `python -m techtrend.daily`.

One command for the Coolify Scheduled Task: runs collect (ingest) -> score ->
enrich in that exact order, in a single process, reusing the existing stage
`main()` functions rather than reimplementing collection/scoring/enrichment.

Fail-fast: the first stage that returns a non-zero exit code halts the chain
and that code becomes this process's exit code -- a failed score stage must
never be followed by enrich running on stale or partial data. Raised
exceptions from a stage propagate as-is (no broad swallowing try/except); the
exit-code path covers graceful non-zero returns.

Named `daily` (not `pipeline`) because `techtrend.pipeline` is a package and a
top-level `techtrend/pipeline.py` module cannot coexist with it.
"""

import logging

from techtrend import enrich, ingest, score
from techtrend.logging_setup import setup_logging

logger = logging.getLogger(__name__)

# Ordered (stage_name, module) pairs. Hold MODULE references, not bound `main`
# functions, so `module.main` is resolved at call time -- keeps each stage
# monkeypatchable by name in tests and honors any future stage-main swap.
STAGES = [
    ("collect", ingest),
    ("score", score),
    ("enrich", enrich),
]


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    for stage_name, module in STAGES:
        logger.info("stage=pipeline:%s status=starting", stage_name)
        code = module.main([])
        if code != 0:
            logger.error(
                "stage=pipeline:%s status=failed exit_code=%d -- chain halted",
                stage_name,
                code,
            )
            return code
        logger.info("stage=pipeline:%s status=complete", stage_name)

    logger.info("stage=pipeline status=complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
