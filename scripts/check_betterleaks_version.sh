#!/usr/bin/env bash
# Fail before any leak scan when the betterleaks on PATH is not the pinned release.
# Other releases ship different default rules and flag the repository's sample values.
# The expected version comes from BETTERLEAKS_VERSION in .devcontainer/Dockerfile, which
# flake.nix pins to the same release; there is intentionally no second constant here.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dockerfile="$script_dir/../.devcontainer/Dockerfile"
fix_hint="Run checks and commits in the Nix shell, for example: nix develop -c task check
or nix develop -c git commit. The DevContainer also provides the pinned release."

fail() {
  echo "betterleaks version check failed: $1" >&2
  echo "$fix_hint" >&2
  exit 1
}

expected=""
if [ -f "$dockerfile" ]; then
  expected="$(sed -nE 's/^ARG BETTERLEAKS_VERSION=v?([0-9]+\.[0-9]+\.[0-9]+)[[:space:]]*$/\1/p' \
    "$dockerfile" | head -n 1)"
fi
if [ -z "$expected" ]; then
  echo "betterleaks version check failed: cannot read ARG BETTERLEAKS_VERSION=vX.Y.Z" \
    "from $dockerfile" >&2
  exit 1
fi

if ! command -v betterleaks >/dev/null 2>&1; then
  fail "expected betterleaks $expected, actual: not installed"
fi

if ! output="$(betterleaks version 2>&1)"; then
  fail "expected betterleaks $expected, actual: 'betterleaks version' failed: $output"
fi
actual="$(printf '%s\n' "$output" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 || true)"
if [ -z "$actual" ]; then
  fail "expected betterleaks $expected, actual: unparseable version output: $output"
fi

if [ "$actual" != "$expected" ]; then
  fail "expected betterleaks $expected, actual: $actual ($(command -v betterleaks))"
fi
