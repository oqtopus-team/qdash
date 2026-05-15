#!/usr/bin/env bash
set -euo pipefail

mkdir -p /home/vscode/.codex /home/vscode/.local
chown -R vscode:vscode /home/vscode/.codex /home/vscode/.local
chmod -R u+rwX /home/vscode/.codex /home/vscode/.local

update-docker-socket-group vscode

exec sleep infinity
