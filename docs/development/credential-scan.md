# Credential Scanning

QDash runs three tools to keep secrets out of the repository: Lefthook orchestrates a pre-commit hook, Betterleaks blocks staged secrets locally before they enter git history, and Trufflehog scans git history in CI for verified leaks.

## Tools

| Tool        | Where it runs                          | What it scans                                   | Configuration                    |
| ----------- | -------------------------------------- | ----------------------------------------------- | -------------------------------- |
| Lefthook    | Local pre-commit                       | Triggers Betterleaks against staged files       | `lefthook.yml`                   |
| Betterleaks | Local pre-commit                       | Pattern match for secrets in working tree       | `.betterleaks.toml`              |
| Trufflehog  | CI only (push, PR to `main`/`develop`) | Git history; only verified secrets are reported | `.trufflehog-exclude-paths.txt`  |

CI definitions live in `.github/workflows/secret-scan.yml`. Installation instructions are in [Setup](./setup.md#secret-scanning-tools).

> Betterleaks is the maintained successor to Gitleaks, by the original Gitleaks author. It is config-compatible: when no `.betterleaks.toml` is present it falls back to `.gitleaks.toml`, honours the `GITLEAKS_CONFIG` env var, reads `.gitleaksignore`, and respects both `betterleaks:allow` and `gitleaks:allow` inline comments.

### Why two scanners

The two tools support different allowlist granularities, which is why they own different stages:

|             | Path allowlist                          | Literal-string allowlist             |
| ----------- | --------------------------------------- | ------------------------------------ |
| Betterleaks | yes (`prefilter` CEL)                   | yes (`filter` CEL, in `.betterleaks.toml`) |
| Trufflehog  | yes (`.trufflehog-exclude-paths.txt`)   | no                                   |

Because Betterleaks can allowlist *specific values*, it can be configured strictly: only the literals matched by the `filter` in `.betterleaks.toml` are exempt — anything else credential-shaped is rejected. That precision makes it the right gate at **pre-commit**, where it blocks credentials before they enter git history.

Trufflehog has no string-level allowlist, so the only way to suppress a known false positive is to drop the entire file. Compensating for that, it **verifies findings by probing the upstream provider** to check whether a credential is live, and walks **full git history** in CI on push and PR. Its role is ongoing detection of live secrets — running on remote CI infrastructure and reaching out to remote providers to confirm validity.

The result is a clear division of labor: Betterleaks is the strict, fast, syntactic gate at commit time; Trufflehog is the slower, semantic, live-credential check that runs in CI. Betterleaks is intentionally not run in CI — the local pre-commit hook covers the syntactic pass, and any commit that slips past it is caught by Trufflehog's history scan, so running it again on every push would only duplicate work.

### Lefthook

`lefthook.yml` defines a single pre-commit command that calls `betterleaks git --pre-commit --staged`. Running `lefthook install` once writes the git hook into `.git/hooks/`. If the Betterleaks binary is missing, Lefthook skips the step rather than failing the commit, so contributors on platforms without the binary are not blocked.

### Betterleaks

Betterleaks scans content for known secret patterns (API keys, tokens, private keys). The repo config `.betterleaks.toml` sets `[extend] useDefault = true` to inherit all built-in detection rules (AWS, GitHub, GCP, Azure, Slack, Stripe, etc.) and layers two CEL-based filters on top:

- **`prefilter`** — a CEL expression evaluated *before* any regex, with access to file/commit metadata only (`attributes`). Used to skip whole files cheaply (the equivalent of a Gitleaks path allowlist).
- **`filter`** — a CEL expression evaluated *after* a regex match, with access to the `finding` (`finding["secret"]`, `finding["match"]`, `finding["line"]`, …). Used to discard specific known-safe values (the equivalent of a Gitleaks regex allowlist).

> **TOML gotcha:** `prefilter` and `filter` are top-level keys and **must appear before** the `[extend]` table in the file. Any key written after a `[table]` header is parsed as part of that table, so placing them after `[extend]` would silently nest them as `extend.prefilter`/`extend.filter` and disable them.

CEL helpers used in our config: `matchesAny(value, [regexes])` returns true if `value` matches any regex; `attributes[?"path"].orValue("")` reads the file path safely.

#### Allowlist entries and why they are safe

Path exemptions (in `prefilter`):

| Entry | Why allowlisting is safe |
| --- | --- |
| `ui/src/client/` | Orval-generated TypeScript API client. Regenerated from `docs/oas/openapi.json` by `task generate`; any hand edit is overwritten on the next run. |
| `ui/src/schemas/` | Orval-generated TypeScript schemas. Same generation lifecycle as `ui/src/client/`. |
| `ui/bun.lock` | Bun lockfile. Contains package integrity values that look high-entropy but are public package digests. Regenerated by `bun install`. |
| `docs/oas/openapi.json` | OpenAPI document exported from the FastAPI app via `curl /openapi.json` in `task generate`. Not hand-edited. |
| `.devcontainer/requirements.txt` | Generated pin file for the dev container. |
| `.betterleaks.toml` | The config file itself, so the literal sample values it contains are not re-scanned. |

Value exemptions (in `filter`):

| Entry | Target | Why allowlisting is safe |
| --- | --- | --- |
| `mongodb://root:example@mongo:27017` | `finding["secret"]` | Local-dev compose default. The hostname `mongo` resolves only inside the compose network and the password is literally the word `example` — it is not a secret in any environment, just an example value. (Gitleaks used `regexTarget = "match"`; Betterleaks captures the clean URI in `finding["secret"]`, so the filter matches there.) |
| `ADMIN_TOKEN`, `YOUR_TOKEN` | `finding["secret"]` | Documentation placeholder token names, not real credentials. |
| `x90_gate_fidelity`, `x180_gate_fidelity`, `zx90_gate_fidelity` | `finding["secret"]` | Quantum gate fidelity metric names that resemble high-entropy tokens. |

The shared property of every path entry is **generation-owned**: the file is rewritten by a tool, not by a human. A developer pasting a real credential into one of these files would lose it on the next regeneration step, so the scanning blind spot has no practical attack surface. The value entries cover fixed sample/placeholder strings that are identical across every developer's machine.

### Trufflehog

Trufflehog walks the git history and reports only **verified** findings — meaning it actively probed the upstream provider and confirmed the credential is live. False positives are rare, so a hit should be treated as a real leak.

Paths in `.trufflehog-exclude-paths.txt` are excluded from history scanning. Each line is a regex matched against the file path:

```
\.betterleaks\.toml
\.gitleaks\.toml
docs/design/api-testing-guidelines\.md
docs/development/api/testing\.md
docs/development/credential-scan\.md
poetry\.lock
scripts/migrate_user_tokens\.py
tests/conftest\.py
```

#### Exclude entries and why they are safe

Because Trufflehog walks **full git history**, the exclude list must cover both currently-tracked files and files that only exist in older commits.

| Entry | Status | Why excluding is safe |
| --- | --- | --- |
| `\.betterleaks\.toml` | tracked | Contains the Betterleaks allowlist itself — the literal `mongodb://root:example@mongo:27017` and placeholder tokens (`ADMIN_TOKEN`, `YOUR_TOKEN`) would otherwise be re-flagged as credentials. None are real secrets; see the Betterleaks allowlist tables above. |
| `\.gitleaks\.toml` | deleted (history only) | Removed when the project migrated from Gitleaks to Betterleaks. Earlier commits still contain it with the same example values, so it stays excluded for history scans. |
| `docs/design/api-testing-guidelines\.md` | deleted (history only) | Removed in commit `50b0fd31`. Old API testing guideline document that referenced example tokens. Excluded so historical commits do not trigger findings. |
| `docs/development/api/testing\.md` | tracked | API testing guide. May reference token names and example fixtures in code samples. None are live credentials. |
| `docs/development/credential-scan\.md` | tracked | This document itself. Contains example tool output with mock values such as `AKIAIOSFODNN7EXAMPLE` and fabricated commit hashes used to illustrate finding format. |
| `poetry\.lock` | deleted (history only) | Removed in commit `e840268b` when the project moved to `uv`. Lockfile entries contain public package integrity digests that look high-entropy. |
| `scripts/migrate_user_tokens\.py` | deleted (history only) | Removed in commit `cca42d62`. One-shot migration script that operated on user-token records; variable names and field-key strings match credential-detector patterns even though no live secret was ever embedded. |
| `tests/conftest\.py` | tracked | Pytest fixtures set environment variables to obvious dummy values (`"test-token"`, `"test-openai-key"`, etc.) so the test client can boot without real credentials. None are real. |

Trufflehog only reports **verified** findings, so unverified pattern matches in these files would not have triggered an action anyway — but excluding them keeps scans quiet and prevents future verifiers (added by Trufflehog upstream) from probing fixture values.

## Running Locally

The repository ships task targets that mirror the CI commands.

| Command                  | What it does                                                |
| ------------------------ | ----------------------------------------------------------- |
| `task scan-leaks`        | Betterleaks over the full git history                       |
| `task scan-leaks-staged` | Betterleaks against staged files only (same as pre-commit)  |
| `task scan-secrets`      | Trufflehog against git history, verified findings only      |
| `task scan-secrets-all`  | Trufflehog against git history, including unverified hits   |

`task check` (the standard pre-push gate) includes `scan-leaks`.

## Reading Output

### Betterleaks

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

**Betterleaks** — extend the CEL filters in `.betterleaks.toml`. Add a path to `prefilter` to skip a whole file, or a value pattern to `filter` to ignore a specific match:

```toml
# Top-level keys MUST come before the [extend] table.

prefilter = '''
matchesAny(attributes[?"path"].orValue(""), [
  r"""path/to/safe/file\.json""",
])
'''

filter = '''
matchesAny(finding["secret"], [
  r"""dev-only-fixture-token-[a-z0-9]+""",
])
'''

[extend]
useDefault = true
```

Prefer narrow `filter` value patterns over broad `prefilter` path entries — a broad path entry hides real future leaks in the same file. For a one-off line, an inline `betterleaks:allow` (or `gitleaks:allow`) comment also works.

**Trufflehog** — add the path regex to `.trufflehog-exclude-paths.txt`. Only do this for files that legitimately contain credential-shaped strings (test fixtures, documentation about credentials). If the finding is verified, do not allowlist; rotate.
