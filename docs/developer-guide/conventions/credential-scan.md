# Credential Scanning

Local scans block credential-shaped content; CI also checks Git history for verified secrets.

## Tools

| Tool | Purpose | Configuration |
| --- | --- | --- |
| Lefthook | Runs the staged scan before commits | `lefthook.yml` |
| Betterleaks | Scans staged files, working files, and branch commits | `.betterleaks.toml` |
| Trufflehog | Verifies historical findings with providers in CI | `.trufflehog-exclude-paths.txt` |

CI runs through `.github/workflows/secret-scan.yml`. A verified scan does not replace the local
pattern scan.

## Running Locally

| Command | Scope |
| --- | --- |
| `task scan-leaks-staged` | Staged contents |
| `task scan-leaks-local` | Tracked working files and commits beyond the target |
| `task scan-leaks` | Full local Git history |
| `task scan-secrets` | Verified history findings |
| `task scan-secrets-all` | Verified and unverified history findings |

Before pushing, stage intended new files, fetch the target, and run `nix develop -c task check`
on the host. Run directly inside the DevContainer. For a target other than `develop`, use
`LEAKS_BASE=origin/<target>`. The local scan reads current working contents, including unstaged
edits; untracked files are excluded until staged. The pre-commit scan reads the index.

## Scanner Version

Checks and commits require the Betterleaks release pinned in `.devcontainer/Dockerfile` and
`flake.nix`. Run host commits inside Nix too: `nix develop -c git commit`.
A missing or mismatched version fails closed. Fix the environment; do not bypass hooks or change
allowlists to accommodate a different scanner. Use `task check-betterleaks-version` to diagnose.
Upgrade both pins together and rerun scans.

## Reading Output

Use the finding's rule, file, line, and fingerprint to locate and classify it. A verified finding
can be an active credential: rotate it before addressing repository history.

## Handling False Positives

Prefer a narrowly scoped value exemption over excluding a whole file. Betterleaks uses CEL
`prefilter` for paths and `filter` for findings; both must be top-level TOML keys before
`[extend]`. Use `finding["rule_id"]`, not `ruleID`.

The checked-in configuration documents existing exemptions. Trufflehog exclusions cover whole
paths, including historical names, so keep them rare. Never allowlist a verified secret.
