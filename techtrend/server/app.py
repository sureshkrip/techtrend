"""Read-only FastAPI dashboard.

The single route (GET /) reads entities/scores/run_manifest through
techtrend.server.queries and renders a Jinja2 template. This module never
imports or calls techtrend.ingest and exposes no route that writes -- the
dashboard is strictly read-only (D-17).
"""

import logging
import sqlite3
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from techtrend.config import load_config
from techtrend.db.connection import connect
from techtrend.server.health import has_successful_collector_run, health_status
from techtrend.server.queries import query_partial_history_count, query_ranked

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

DB_UNREADABLE_MESSAGE = (
    "Dashboard couldn't read the database — check `techtrend.db` exists and try again."
)

app = FastAPI()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, sort: str = "velocity") -> HTMLResponse:
    """CR-03 fix: `load_config()` and `connect()` are both fallible (a
    malformed config/tracked.toml or a corrupted techtrend.db) and must
    degrade to `DB_UNREADABLE_MESSAGE`, never a raw framework traceback
    (UI-SPEC "Error state — DB unreadable"). Both calls now live inside the
    same try/except boundary as the query calls -- neither happens in a
    FastAPI dependency (which a route's own try/except cannot cover) nor
    before the try: block starts.
    """
    db_error = None
    rows: list[sqlite3.Row] = []
    applied_sort = sort
    partial_history_count = 0
    health = None
    has_successful_run = False
    conn: sqlite3.Connection | None = None

    try:
        config = load_config()
        conn = connect()
        rows, applied_sort = query_ranked(conn, sort=sort)
        partial_history_count = query_partial_history_count(conn, config.tunables.window_days)
        health = health_status(conn, config, datetime.now(UTC))
        # V2/D-08a: table.html needs this to distinguish "no run has
        # completed yet" (truly empty install) from "a run completed but
        # nothing is eligible to rank yet" (D-08a's expected first-week
        # sparseness) -- the latter must never render the "run ingest"
        # empty state, which would be false.
        has_successful_run = has_successful_collector_run(conn)
    except (sqlite3.Error, OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        logger.warning("stage=dashboard status=read_failed error=%s", exc)
        db_error = DB_UNREADABLE_MESSAGE
    finally:
        if conn is not None:
            conn.close()

    template_name = "partials/table.html" if request.headers.get("HX-Request") else "dashboard.html"
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "rows": rows,
            "sort": applied_sort,
            "partial_history_count": partial_history_count,
            "health": health,
            "db_error": db_error,
            "has_successful_run": has_successful_run,
        },
    )
