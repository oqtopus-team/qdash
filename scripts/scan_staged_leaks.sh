#!/usr/bin/env bash
set -euo pipefail

if ! command -v betterleaks >/dev/null 2>&1; then
  echo "betterleaks not installed; skipping staged leak scan" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

scan_root="$tmpdir/staged"
policy_dir="$tmpdir/policy"
mkdir -p "$scan_root" "$policy_dir"
config_path="$policy_dir/.betterleaks.toml"
ignore_path="$policy_dir/.betterleaksignore"
staged_paths="$policy_dir/staged-paths"

git -C "$repo_root" show ":.betterleaks.toml" >"$config_path"
if git -C "$repo_root" cat-file -e ":.betterleaksignore" 2>/dev/null; then
  git -C "$repo_root" show ":.betterleaksignore" \
    | sed -E 's/^[0-9a-f]{40}://' >"$ignore_path"
else
  : >"$ignore_path"
fi

if ! git -C "$repo_root" diff --cached --name-only -z --diff-filter=ACMRT >"$staged_paths"; then
  echo "failed to enumerate staged files for leak scan" >&2
  exit 1
fi

staged_count=0
while IFS= read -r -d '' path; do
  case "$path" in
    */) continue ;;
  esac

  mkdir -p "$scan_root/$(dirname "$path")"
  git -C "$repo_root" show ":$path" >"$scan_root/$path"
  staged_count=$((staged_count + 1))
done <"$staged_paths"

if [ "$staged_count" -eq 0 ]; then
  echo "no staged files to scan"
  exit 0
fi

(
  cd "$scan_root"
  betterleaks dir . \
    --config "$config_path" \
    --gitleaks-ignore-path "$ignore_path" \
    "$@"
)
