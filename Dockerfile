# TechTrend dashboard image. uv-managed, Python 3.13.
# Serves the read-only FastAPI dashboard; the daily ingest+score job runs as a
# Coolify Scheduled Task inside this same container (shares the /data volume).
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Compile bytecode at build time; copy (not hardlink) into the venv since the
# build cache and target may sit on different mounts.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 1) Dependencies as their own cached layer — only re-runs when the lockfile
#    changes, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 2) App source + install the project itself.
COPY . .
RUN uv sync --frozen --no-dev

# Put the venv on PATH so `uvicorn` / `python -m techtrend.ingest` resolve
# directly (the Coolify scheduled task calls the latter).
ENV PATH="/app/.venv/bin:$PATH"

# All mutable state (SQLite DB, HTTP cache, logs) lives here — mount a Coolify
# persistent volume at /data so it survives redeploys. Without the volume this
# dir is ephemeral and history is wiped on every deploy.
ENV TECHTREND_DATA_DIR=/data
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Read-only dashboard. Never triggers a pipeline run on request (D-17); the
# daily collection is a separate scheduled command, not part of serving.
CMD ["uvicorn", "techtrend.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
