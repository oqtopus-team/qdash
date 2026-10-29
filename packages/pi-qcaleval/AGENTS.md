# pi-qcaleval

This package supplies calibration-evaluation tools and skills to pi CLI and the
QDash Agent Runtime. Follow the repository-root `AGENTS.md` for shared policies,
branches, checks, commits, and documentation. See the
[pi extension design guide](../../docs/developer-guide/copilot/extensions.md)
for architecture and the [package guide](../../docs/developer-guide/copilot/packages.md)
for development and releases.

- Keep model selection, question templates, request construction, and answer parsing
  in `extensions/`; keep reusable calibration guidance in `skills/`.
- Preserve the package's independence from the QDash client.
- Never print model credentials in tool output or include them in fixtures.
- Update `../../docs/reference/pi-qcaleval.md` when tool inputs or outputs change.
- Add focused tests under `tests/` when changing templates, model selection, or parsing.
