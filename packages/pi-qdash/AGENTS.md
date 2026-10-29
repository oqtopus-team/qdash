# pi-qdash

This package supplies QDash tools and skills to pi CLI and the QDash Agent Runtime.
Follow the repository-root AGENTS.md for branches, checks, commits, and documentation.

- Install dependencies with `bun install --frozen-lockfile` from the repository root.
- Run `task ci-pi-packages` and `task ci-agent-runtime` after changes.
- Keep API access, redaction, rendering, and mechanical evidence extraction in `extensions/`.
- Keep calibration interpretation and workflows in `skills/`.
- New tools are read-only by default. Writes follow the existing approval gates.
- Never print tokens, passwords, or Cloudflare Access secrets in tool output.
- Update `../../docs/reference/pi-qdash.md` when tools or commands change.
- Keep `extensions/qdash.ts` thin; helpers live in `extensions/lib/`, domain tools in `extensions/tools/`.
- Package release instructions live in `../../docs/developer-guide/copilot/packages.md`.
