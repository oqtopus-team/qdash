# Development Guide

The pi-qdash package is developed in the QDash monorepo and remains usable from pi CLI.

## Local development

Use Node.js 24, Bun 1.4, and an authenticated pi installation. Clone QDash,
create a feature branch from `develop`, and run these commands from its root:

```bash
bun install --frozen-lockfile
task ci-pi-packages
task ci-agent-runtime
pi -e ./packages/pi-qdash
```

Configure access with `QDASH_*` variables or `~/.config/qdash/config.ini`.
In interactive pi, use `/qdash-config <profile>`, `/qdash-setup <profile> <chip_id>`,
and `/qdash-dashboard` to check connectivity.

Open PRs against `oqtopus-team/qdash:develop`. Follow the root `AGENTS.md`,
including `task check` before every push. See the
[package release guide](../../../docs/developer-guide/copilot/packages.md)
for independent npm releases.

## What to change where

Use this split when designing features:

### Extension/tool layer

See [Architecture](./ARCHITECTURE.md) for the module layout and refactor direction.

Use `extensions/qdash.ts` and extracted modules under `extensions/lib/` for safe, mechanical capabilities:

- QDash API access through `@oqtopus-team/qdash-client`
- redaction and safety gates
- TUI rendering
- read-only data extraction helpers
- confirmation-gated write operations

New tools should be read-only by default. Write/operational tools must follow the existing approval-gate pattern (`confirmWrite: true` for non-interactive runs).

### Skills layer

Use `skills/` for domain reasoning and workflows:

- calibration diagnosis recipes
- runbooks and decision policies
- thresholds and failure-mode taxonomy
- known calibration cases
- guidance for how agents should combine tool outputs

For example, `qdash_analyze_figure_json` belongs in the extension because it mechanically summarizes Plotly JSON; interpreting a bad Bell tomography result belongs in `skills/qdash-two-qubit-calibration-diagnosis/`.

### Docs

Update docs with feature changes:

- Tools: `docs/tools.md`
- Commands and bundled skills: `docs/commands.md`
- Contributor/development process: `docs/DEVELOPMENT.md` and `docs/CONTRIBUTING.md`
- Architecture and refactor direction: `docs/ARCHITECTURE.md`
- Agent-facing project policy: `AGENTS.md`

## Using pi to develop this repository

This repository includes `AGENTS.md`, which pi reads as project-specific guidance. It describes layout, commands, safety policies, and the extension-vs-skill split. When using pi for development, start it from the repository root:

```bash
pi
```

Useful prompts:

```text
Read AGENTS.md and propose where this feature should live: extension or skill.
Add a read-only QDash helper tool and update docs/tools.md.
Add a calibration diagnosis case to the appropriate skill and run `task ci-pi-packages`.
```

When testing local extension behavior inside pi, use:

```bash
pi -e .
```

If pi is already running after edits to skills/extensions, use:

```text
/reload
```

## QDash credentials and safety

Never commit QDash tokens, Cloudflare Access secrets, passwords, or local config files. The extension redacts secrets in tool output, but contributors should still avoid placing secrets in test fixtures, docs examples, issue comments, or PR descriptions.

For write or operational behavior, prefer dry-run/read-only plans first and require explicit human confirmation before task execution, candidate commit, or backend apply.
