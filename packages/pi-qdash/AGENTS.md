# pi-qdash

This package supplies QDash tools and skills to pi CLI and the QDash Agent Runtime.
Follow the repository-root `AGENTS.md` for shared policies, branches, checks,
commits, and documentation. See the [pi extension design guide](../../docs/developer-guide/copilot/extensions.md)
for architecture and the [package guide](../../docs/developer-guide/copilot/packages.md)
for development and releases.

- Keep API access, redaction, rendering, and mechanical evidence extraction in `extensions/`.
- Keep calibration interpretation and workflows in `skills/`.
- New tools are read-only by default. Writes follow the existing approval gates.
- Never print tokens, passwords, or Cloudflare Access secrets in tool output.
- Update `../../docs/reference/pi-qdash.md` when tools or commands change.
- Keep `extensions/qdash.ts` thin; helpers live in `extensions/lib/`, domain tools in `extensions/tools/`.
