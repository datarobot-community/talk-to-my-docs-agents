#!/usr/bin/env bash

# start-app.sh boots the web application in two modes:
#   1. Pre-bundled execution environment (identified by /.datarobot-pre-bundled)
#      └ uses system-wide dependencies baked into the custom image.
#   2. Default DataRobot base environment
#      └ creates a venv via `uv sync` and runs via `uv run`.

# Configure environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}${SCRIPT_DIR}/core/src"
export UV_CACHE_DIR=.uv

if [ -f "/.datarobot-pre-bundled" ]; then
    # Dependencies are installed system-wide in the custom execution environment,
    # so we can call the interpreter directly without uv.
    python alembic_migration.py  # migrating base to the last change
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --timeout-keep-alive 300
else
    if [ ! -d ".venv" ]; then
        uv sync
    fi
    # The base environment creates a project-scoped venv; run via uv so it activates it.
    uv run python alembic_migration.py
    uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --timeout-keep-alive 300
fi
