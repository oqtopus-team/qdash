#!/usr/bin/env bash
set -euo pipefail

if ! command -v betterleaks >/dev/null 2>&1; then
  echo "betterleaks not installed; skipping staged leak scan"
  exit 0
fi

repo_root="$(git rev-parse --show-toplevel)"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

staged_count=0
while IFS= read -r -d '' path; do
  case "$path" in
    */) continue ;;
  esac

  mkdir -p "$tmpdir/$(dirname "$path")"
  git -C "$repo_root" show ":$path" >"$tmpdir/$path"
  staged_count=$((staged_count + 1))
done < <(git -C "$repo_root" diff --cached --name-only -z --diff-filter=ACMRT)

if [ "$staged_count" -eq 0 ]; then
  echo "no staged files to scan"
  exit 0
fi

betterleaks dir "$tmpdir" \
  --config "$repo_root/.betterleaks.toml" \
  --gitleaks-ignore-path "$repo_root/.betterleaksignore" \
  "$@"
