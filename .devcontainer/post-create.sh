#!/usr/bin/env bash
set -euo pipefail

mkdir -p /root/.cache/pip /root/.cache/uv /workspace/qdash/ui/node_modules
chmod -R u+rwX /root/.cache/pip /root/.cache/uv /workspace/qdash/ui/node_modules

cd /workspace/qdash

uv sync --locked --all-groups --all-packages

cd /workspace/qdash/ui
bun install --frozen-lockfile

cd /workspace/qdash
lefthook install
