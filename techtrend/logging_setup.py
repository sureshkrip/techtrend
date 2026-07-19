"""Structured console + file logging for the daily ingestion job.

RESEARCH.md Pitfall 8: establishing a log file now is what makes Phase 4's
headless Task Scheduler run debuggable later — cheap to set up now, awkward
to retrofit. The formatter must never receive an Authorization header value;
log GitHub status codes and messages only.
"""

import logging
from pathlib import Path

DEFAULT_LOGFILE = Path("logs/techtrend.log")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(logfile: Path | None = None) -> None:
    """Configure the stdlib root logger with a FileHandler and a StreamHandler.

    Creates the log directory if it does not already exist. Idempotent-ish:
    safe to call more than once (existing handlers are replaced, not stacked).
    """
    resolved = logfile if logfile is not None else DEFAULT_LOGFILE
    resolved.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.FileHandler(resolved, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Replace any previously configured handlers rather than stacking duplicates.
    root.handlers = [file_handler, stream_handler]
