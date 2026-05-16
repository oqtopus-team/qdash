#!/usr/bin/env bash
set -euo pipefail

mkdir -p /root/.codex /root/.local
mkdir -p /root/.cache/pip /root/.cache/uv /workspace/qdash/ui/node_modules
chmod -R u+rwX \
  /root/.codex \
  /root/.local \
  /root/.cache/pip \
  /root/.cache/uv \
  /workspace/qdash/ui/node_modules

git config --global --add safe.directory /workspace/qdash

grep -q 'umask 022' ~/.bashrc || echo 'umask 022' >> ~/.bashrc
grep -q 'umask 022' ~/.zshrc || echo 'umask 022' >> ~/.zshrc
