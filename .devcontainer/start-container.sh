#!/usr/bin/env bash
set -euo pipefail

update-docker-socket-group vscode

mkdir -p \
  /commandhistory \
  /home/vscode/.cache/pip \
  /home/vscode/.cache/uv \
  /home/vscode/.cache/ruff \
  /home/vscode/.cache/mypy \
  /home/vscode/.cache/pytest \
  /home/vscode/.cache/coverage \
  /workspace/qdash/.venv \
  /workspace/qdash/ui/.next \
  /home/vscode/.claude \
  /home/vscode/.codex \
  /home/vscode/.local \
  /home/vscode/.vscode-server/extensions \
  /opt/codex
chown -R vscode:vscode \
  /commandhistory \
  /home/vscode/.cache \
  /workspace/qdash/.venv \
  /workspace/qdash/ui/.next \
  /home/vscode/.claude \
  /home/vscode/.codex \
  /home/vscode/.local \
  /home/vscode/.vscode-server \
  /opt/codex

exec sleep infinity
