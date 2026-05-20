#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${1:-vscode}"
DOCKER_SOCKET="/var/run/docker.sock"

if [ ! -S "${DOCKER_SOCKET}" ]; then
  exit 0
fi

SOCKET_GID="$(stat -c '%g' "${DOCKER_SOCKET}")"
SOCKET_GROUP="$(getent group "${SOCKET_GID}" | cut -d: -f1 || true)"

if [ -z "${SOCKET_GROUP}" ]; then
  SOCKET_GROUP="docker-host"
  if getent group "${SOCKET_GROUP}" >/dev/null; then
    groupmod --gid "${SOCKET_GID}" "${SOCKET_GROUP}"
  else
    groupadd --gid "${SOCKET_GID}" "${SOCKET_GROUP}"
  fi
fi

usermod --append --groups "${SOCKET_GROUP}" "${REMOTE_USER}"
