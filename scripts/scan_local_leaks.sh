#!/usr/bin/env bash
set -euo pipefail

if ! command -v betterleaks >/dev/null 2>&1; then
  echo "betterleaks not installed; cannot run local leak scan" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
base="${LEAKS_BASE:-origin/develop}"
if ! base_sha="$(git rev-parse --verify --end-of-options "$base^{commit}")"; then
  echo "Cannot resolve LEAKS_BASE=$base; fetch the target branch or set LEAKS_BASE." >&2
  exit 1
fi
if [ "$(git rev-parse --is-shallow-repository)" = true ]; then
  echo "Local leak scan requires full history; run git fetch --unshallow first." >&2
  exit 1
fi
if ! git merge-base "$base_sha" HEAD >/dev/null; then
  echo "LEAKS_BASE=$base and HEAD have no common ancestor." >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
scan_root="$tmpdir/working"
mkdir -p "$scan_root"
git ls-files --cached -z >"$tmpdir/paths"
while IFS= read -r -d '' path; do
  # Deleted files, symlinks, and submodule directories are not regular source files.
  if [ -f "$path" ] && [ ! -L "$path" ]; then
    mkdir -p "$scan_root/$(dirname "$path")"
    cp -- "$path" "$scan_root/$path"
  fi
done <"$tmpdir/paths"

# Directory fingerprints omit the commit prefix used by history findings.
ignore_path="$tmpdir/.betterleaksignore"
if [ -f .betterleaksignore ]; then
  sed -E 's/^[0-9a-f]{40}://' .betterleaksignore >"$ignore_path"
else
  : >"$ignore_path"
fi

status=0
echo "Scanning tracked working files (stage new files with git add to include them)"
(
  cd "$scan_root"
  betterleaks dir . --config "$repo_root/.betterleaks.toml" \
    --gitleaks-ignore-path "$ignore_path" --redact --verbose
) || status=$?

echo "Scanning commits in $base..HEAD"
GIT_CONFIG_COUNT=1 \
  GIT_CONFIG_KEY_0=safe.directory \
  GIT_CONFIG_VALUE_0="$repo_root" \
  betterleaks git "$(git rev-parse --absolute-git-dir)" \
    --log-opts="$base_sha..HEAD" --config .betterleaks.toml \
    --redact --verbose || status=$?
exit "$status"
