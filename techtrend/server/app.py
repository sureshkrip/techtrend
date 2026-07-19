"""Read-only FastAPI dashboard.

The single route (GET /) reads entities/scores/run_manifest through
techtrend.server.queries and renders a Jinja2 template. This module never
imports or calls techtrend.ingest and exposes no route that writes -- the
dashboard is strictly read-only (D-17).
"""

import sqlite3
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from techtrend.db.connection import connect
from techtrend.server.queries import query_latest_run, query_ranked

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

DB_UNREADABLE_MESSAGE = (
    "Dashboard couldn't read the database — check `techtrend.db` exists and try again."
)

app = FastAPI()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_conn():
    """Yield one connection per request; never a shared cross-thread connection."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    sort: str = "velocity",
    conn: sqlite3.Connection = Depends(get_conn),  # noqa: B008 -- FastAPI's own DI idiom
) -> HTMLResponse:
    db_error = None
    rows: list[sqlite3.Row] = []
    latest_run = None

    try:
        rows = query_ranked(conn, sort=sort)
        latest_run = query_latest_run(conn)
    except sqlite3.Error:
        db_error = DB_UNREADABLE_MESSAGE

    template_name = "partials/table.html" if request.headers.get("HX-Request") else "dashboard.html"
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "rows": rows,
            "sort": sort,
            "latest_run": latest_run,
            "db_error": db_error,
        },
    )
