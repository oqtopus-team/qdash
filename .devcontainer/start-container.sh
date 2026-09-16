#!/usr/bin/env bash
set -euo pipefail

update-docker-socket-group vscode

mkdir -p \
  /commandhistory \
  /home/vscode/.cache/pip \
  /home/vscode/.cache/uv \
  /home/vscode/.claude \
  /home/vscode/.codex \
  /home/vscode/.local \
  /home/vscode/.vscode-server/extensions \
  /opt/codex
chown -R vscode:vscode \
  /commandhistory \
  /home/vscode/.cache \
  /home/vscode/.claude \
  /home/vscode/.codex \
  /home/vscode/.local \
  /home/vscode/.vscode-server \
  /opt/codex

exec sleep infinity
