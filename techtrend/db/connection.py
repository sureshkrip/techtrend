"""psycopg3 connection helper and schema bootstrap.

RESEARCH.md's concurrency note: one connection per caller, never a shared
cross-thread connection.
"""

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(conninfo: str | None = None) -> psycopg.Connection:
    """Open a psycopg3 connection with dict-row results.

    Preserves the zero-arg call form (`connect()` in production). When
    `conninfo` is None, the connection is built from five discrete env vars:
    PGHOST (default "localhost"), PGPORT (default "5432"), PGDATABASE
    (default "techtrend"), PGUSER (default "techuser"), and PGPASSWORD (read
    from the environment, no default -- may be absent). This is the ONLY
    read of PGPASSWORD anywhere in techtrend/** (mirroring how
    ANTHROPIC_API_KEY lives only in pipeline/llm.py and OPENAI_API_KEY only
    in pipeline/llm_openai.py).

    When `conninfo` is provided (the test fixture's injection seam), it is
    used verbatim and no PG* env vars are read.

    Sets row_factory=dict_row so every existing `row["col"]` / `dict(row)`
    call site keeps working.
    """
    if conninfo is None:
        host = os.environ.get("PGHOST", "localhost")
        port = os.environ.get("PGPORT", "5432")
        dbname = os.environ.get("PGDATABASE", "techtrend")
        user = os.environ.get("PGUSER", "techuser")
        password = os.environ.get("PGPASSWORD")
        conninfo = psycopg.conninfo.make_conninfo(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            **({"password": password} if password else {}),
        )

    return psycopg.connect(conninfo, row_factory=dict_row)


def init_db(conn: psycopg.Connection) -> None:
    """Bootstrap the five-table schema. Idempotent -- safe to call more than once."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.cursor().execute(schema_sql)
    conn.commit()
