#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p /home/vscode/.codex /home/vscode/.local
sudo mkdir -p /home/vscode/.cache/pip /home/vscode/.cache/uv /workspace/qdash/ui/node_modules
sudo chown -R vscode:vscode \
  /home/vscode/.codex \
  /home/vscode/.local \
  /home/vscode/.cache/pip \
  /home/vscode/.cache/uv \
  /workspace/qdash/ui/node_modules
chmod -R u+rwX \
  /home/vscode/.codex \
  /home/vscode/.local \
  /home/vscode/.cache/pip \
  /home/vscode/.cache/uv \
  /workspace/qdash/ui/node_modules

git config --global --add safe.directory /workspace/qdash

grep -q 'umask 022' ~/.bashrc || echo 'umask 022' >> ~/.bashrc
grep -q 'umask 022' ~/.zshrc || echo 'umask 022' >> ~/.zshrc
