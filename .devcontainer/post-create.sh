#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p \
  "${HOME}/.cache/pip" \
  "${HOME}/.cache/uv" \
  /commandhistory \
  /workspace/qdash/ui/node_modules
sudo chown -R "$(id -u):$(id -g)" \
  "${HOME}/.cache" \
  /commandhistory \
  /workspace/qdash/ui/node_modules

cd /workspace/qdash

uv sync --locked --all-groups --all-packages

cd /workspace/qdash/ui
bun install --frozen-lockfile

cd /workspace/qdash
lefthook install
