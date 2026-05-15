#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p /home/vscode/.cache/pip /home/vscode/.cache/uv /workspace/qdash/ui/node_modules
sudo chown -R vscode:vscode \
  /home/vscode/.cache/pip \
  /home/vscode/.cache/uv \
  /workspace/qdash/ui/node_modules
chmod -R u+rwX /home/vscode/.cache/pip /home/vscode/.cache/uv /workspace/qdash/ui/node_modules

cd /workspace/qdash

uv sync --all-groups

cd /workspace/qdash/ui
bun install --frozen-lockfile

cd /workspace/qdash
lefthook install
