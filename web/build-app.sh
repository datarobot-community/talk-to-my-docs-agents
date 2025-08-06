#!/usr/bin/env sh
apt-get update && apt-get install -y --no-install-recommends libreoffice libreoffice-java-common libgtk2.0-dev
apt-get clean
python3 -m pip install --no-cache-dir pipx
PIPX_GLOBAL_BIN_DIR=/usr/bin python3 -m pipx install --global uv
export UV_CACHE_DIR=.uv
uv sync
