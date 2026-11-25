#!/usr/bin/env bash
set -euo pipefail

# Check the scanner release before reading any content.
bash "$(dirname "${BASH_SOURCE[0]}")/check_betterleaks_version.sh"

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
# Select with shell builtins only; a subprocess per path dominated the scan time.
copy_list="$tmpdir/copy-paths"
copy_count=0
while IFS= read -r -d '' path; do
  # Deleted files, symlinks, and submodule directories are not regular source files.
  if [ -f "$path" ] && [ ! -L "$path" ]; then
    # The ./ prefix keeps names that start with - from being read as tar options.
    printf './%s\0' "$path"
    copy_count=$((copy_count + 1))
  fi
done <"$tmpdir/paths" >"$copy_list"

# Copy the working tree bytes of the selected files with one tar pipe. COPYFILE_DISABLE
# keeps macOS metadata out of the archive. A file that disappears or cannot be read fails
# the pipe, and pipefail fails the scan.
tar_format=()
case "$(tar --version 2>/dev/null || true)" in
  *"GNU tar"*) ;;
  # bsdtar rewrites non-ASCII names to another Unicode form on macOS unless pax headers
  # carry the names as raw bytes.
  *) tar_format=(--format pax --options hdrcharset=BINARY) ;;
esac
if [ "$copy_count" -gt 0 ]; then
  COPYFILE_DISABLE=1 tar -cf - ${tar_format[@]+"${tar_format[@]}"} --no-recursion --null -T "$copy_list" \
    | tar -xf - -C "$scan_root"
fi
# Count NUL terminators so file names with newlines are counted once.
copied_count="$(find "$scan_root" -type f -print0 | tr -dc '\000' | wc -c | tr -d '[:space:]')"
if [ "$copied_count" -ne "$copy_count" ]; then
  echo "Leak scan snapshot has $copied_count of $copy_count tracked files; aborting." >&2
  exit 1
fi

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
