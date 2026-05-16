#!/usr/bin/env bash
set -euo pipefail

mkdir -p /root/.codex /root/.local
chmod -R u+rwX /root/.codex /root/.local

exec sleep infinity
