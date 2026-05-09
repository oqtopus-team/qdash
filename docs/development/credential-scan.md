# Credential Scanning

QDash runs three tools to keep secrets out of the repository: Lefthook orchestrates a pre-commit hook, Gitleaks blocks staged secrets locally and in CI, and Trufflehog scans git history in CI for verified leaks.

## Tools

| Tool       | Where it runs                          | What it scans                                   | Configuration                    |
| ---------- | -------------------------------------- | ----------------------------------------------- | -------------------------------- |
| Lefthook   | Local pre-commit                       | Triggers Gitleaks against staged files          | `lefthook.yml`                   |
| Gitleaks   | Local pre-commit + CI (push, PR)       | Pattern match for secrets in working tree       | `.gitleaks.toml`                 |
| Trufflehog | CI only (push, PR to `main`/`develop`) | Git history; only verified secrets are reported | `.trufflehog-exclude-paths.txt`  |

CI definitions live in `.github/workflows/secret-scan.yml`. Installation instructions are in [Setup](./setup.md#secret-scanning-tools).

### Lefthook

`lefthook.yml` defines a single pre-commit command that calls `gitleaks protect --staged`. Running `lefthook install` once writes the git hook into `.git/hooks/`. If the Gitleaks binary is missing, Lefthook skips the step rather than failing the commit, so contributors on platforms without the binary are not blocked.

### Gitleaks

Gitleaks scans content for known secret patterns (API keys, tokens, private keys). The repo overrides the default config via `.gitleaks.toml`, which does two things:

- **`paths`** allowlists generated and lockfile artifacts (`ui/src/client/`, `ui/src/schemas/`, `ui/bun.lock`, `docs/oas/openapi.json`, `.devcontainer/requirements.txt`) so churn there does not produce noise.
- **`regexes`** allowlists the local development MongoDB connection string (`mongodb://USER:PASSWORD@HOST:PORT`), which is a fixed dev credential, not a secret. The exact value lives in `.gitleaks.toml`.

### Trufflehog

Trufflehog walks the git history and reports only **verified** findings — meaning it actively probed the upstream provider and confirmed the credential is live. False positives are rare, so a hit should be treated as a real leak.

Paths in `.trufflehog-exclude-paths.txt` are excluded from history scanning. Each line is a regex matched against the file path:

```
scripts/migrate_user_tokens\.py
docs/design/api-testing-guidelines\.md
tests/conftest\.py
\.gitleaks\.toml
```

## Running Locally

The repository ships task targets that mirror the CI commands.

| Command                  | What it does                                              |
| ------------------------ | --------------------------------------------------------- |
| `task scan-leaks`        | Gitleaks against the full working tree                    |
| `task scan-leaks-staged` | Gitleaks against staged files only (same as pre-commit)   |
| `task scan-secrets`      | Trufflehog against git history, verified findings only    |
| `task scan-secrets-all`  | Trufflehog against git history, including unverified hits |

`task check` (the standard pre-push gate) includes `scan-leaks`.

## Reading Output

### Gitleaks

A finding looks like:

```
Finding:     AKIAIOSFODNN7EXAMPLE
Secret:      AKIAIOSFODNN7EXAMPLE
RuleID:      aws-access-token
Entropy:     3.95
File:        src/qdash/api/config.py
Line:        42
Commit:      (staged)
Author:      <staged>
Date:        (staged)
Fingerprint: src/qdash/api/config.py:aws-access-token:42
```

Key fields when triaging:

- **RuleID** — which detector matched. Gives an immediate hint at the secret type.
- **File / Line** — where to look. For staged scans, the line number is in the working tree.
- **Fingerprint** — stable identifier for the finding; use it if you need to discuss a specific hit.

The exit code is non-zero on any finding, which is what blocks the commit.

### Trufflehog

A verified finding looks like:

```
Found verified result 🐷🔑
Detector Type: AWS
Decoder Type: PLAIN
Raw result: AKIA****************
File: src/qdash/api/legacy.py
Line: 87
Commit: 3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a
Repository: file://.
Email: dev@example.com
Timestamp: 2024-08-12 14:22:10 +0000
```

Because Trufflehog only flags verified secrets, **the credential is almost certainly active**. Rotate it before doing anything else; the git history rewrite comes after.

## Handling False Positives

**Gitleaks** — add the path or regex to `.gitleaks.toml` under `[allowlist]`:

```toml
[allowlist]
  paths = [
    '''path/to/safe/file\.json''',
  ]
  regexes = [
    '''dev-only-fixture-token-[a-z0-9]+''',
  ]
```

Prefer narrow regexes over broad path allowlists — broad allowlists hide real future leaks in the same file.

**Trufflehog** — add the path regex to `.trufflehog-exclude-paths.txt`. Only do this for files that legitimately contain credential-shaped strings (test fixtures, documentation about credentials). If the finding is verified, do not allowlist; rotate.

## Responding to a Real Leak

1. **Rotate the credential immediately.** Anything pushed to a remote should be assumed compromised, even if the commit was reverted.
2. Remove the secret from the working tree and commit the fix.
3. Decide whether history rewriting is warranted. For public repos with verified hits, rewrite (`git filter-repo`) and force-push after coordinating with the team. For private repos where rotation is sufficient, leaving history alone is often the pragmatic choice.
4. Open an internal ticket recording what leaked, when, and what was rotated.
