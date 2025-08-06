#!/usr/bin/env bash

# Configure environment
export UV_CACHE_DIR=.uv

uv run fastapi run --port 8080 --proxy-headers
