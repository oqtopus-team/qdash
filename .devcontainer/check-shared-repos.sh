#!/usr/bin/env sh
set -eu

workspace=${1:-.}
shared_repos_dir=${QDASH_SHARED_REPOS_DIR:-"$workspace/.."}

if [ -z "${QDASH_SHARED_REPOS_DIR:-}" ] && [ -f "$workspace/.env" ] \
  && grep -Eq '^[[:space:]]*QDASH_SHARED_REPOS_DIR[[:space:]]*=' "$workspace/.env"; then
  echo 'Export QDASH_SHARED_REPOS_DIR in the host environment, not only in .env.' >&2
  exit 1
fi

if [ -n "${QDASH_SHARED_REPOS_DIR:-}" ]; then
  case "$QDASH_SHARED_REPOS_DIR" in
    /*) ;;
    *) echo 'QDASH_SHARED_REPOS_DIR must be an absolute host path' >&2; exit 1 ;;
  esac
fi

if [ ! -d "$shared_repos_dir" ]; then
  echo "Shared repository directory does not exist: $shared_repos_dir" >&2
  echo 'Create it on the host before starting the DevContainer.' >&2
  exit 1
fi

if [ ! -w "$shared_repos_dir" ]; then
  echo "Shared repository directory is not writable: $shared_repos_dir" >&2
  exit 1
fi
