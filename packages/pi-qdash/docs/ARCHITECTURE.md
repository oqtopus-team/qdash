# Architecture

`pi-qdash` is a pi package with one extension entry point and bundled skills.

## Design goals

- Keep QDash access safe and predictable.
- Keep write operations approval-gated.
- Keep domain reasoning in skills, not hidden inside tools.
- Make read-only evidence extraction easy to compose from agents.

## Layers

### Extension entry point

`extensions/qdash.ts` remains the package entry point registered in `package.json`.
It wires together tools, commands, TUI renderers, and shared QDash context.

The entry point should get thinner over time. New self-contained logic should be
added under `extensions/lib/` or future `extensions/tools/` modules instead of
adding more large helper blocks to the entry file.

### `extensions/lib/`

Shared implementation modules live here:

- `figure-analysis.ts` — pure read-only Plotly JSON summarization used by diagnostic tools.
- `investigation-context.ts` — validation and summaries for reusable generic timeseries investigation presets.
- `figures.ts` — figure download metadata, text summaries, and TUI image rendering helpers.
- `forum-render.ts` — Forum payload extraction and compact list/detail text/TUI rendering helpers.
- `links.ts` — QDash Web URL/link decoration helpers and safe non-secret config summaries.
- `payload.ts` — common payload/list extraction and compact formatting helpers.
- `render.ts` — shared ANSI/text box, wrapping, compact date/number, and simple TUI text component helpers.
- `results.ts` — tool result formatting and secret redaction.
- `timeseries-plot.ts` — task-result timeseries extraction and compact terminal plot rendering.
- `timeseries-analysis.ts` — generic CSV mapping, time alignment, transforms, correlation, and shared-period fitting.
- `wiring-analysis.ts` — pure cooldown wiring markdown parsing and attenuation insight rendering.
- `write-gate.ts` — central approval gate for QDash write/operational tools.

Prefer small modules with narrow responsibilities. Modules in this layer should
not encode calibration policy beyond mechanical extraction/safety checks.

### Tool layer

Domain-specific tool registration modules may live under `extensions/tools/`.
`extensions/tools/timeseries.ts` registers generic QDash/local-CSV timeseries
comparison while delegating pure alignment/statistics to `extensions/lib/`.

Tools should expose capabilities and structured evidence:

- read-only QDash queries
- figure/raw-data summaries
- dashboard/report builders
- confirmation-gated operational calls

New tools should be read-only by default. If a tool writes, starts tasks, commits
parameters, applies backend configuration, or publishes Forum content, it must use
the approval-gate pattern.

### Skills layer

Skills are the domain-reasoning layer:

- diagnosis recipes
- failure-mode interpretation
- runbook policies
- known calibration cases
- guidance for how agents combine tool outputs

For example, `qdash_analyze_figure_json` mechanically summarizes a Plotly JSON
figure. The interpretation that high `|10>` population indicates a possible
ZX90 angle/phase/cancel issue belongs in `skills/qdash-two-qubit-calibration-diagnosis/`.

## Current refactor direction

The extension started as a single-file implementation. The preferred migration is
incremental and behavior-preserving:

1. Move pure helper logic into `extensions/lib/`.
2. Keep safety-sensitive gates centralized.
3. Move figure and analysis helpers out of the entry point.
4. Continue splitting tool registration by domain (timeseries is already
   extracted):
   - `extensions/tools/figures.ts`
   - `extensions/tools/tasks.ts`
   - `extensions/tools/agent.ts`
   - `extensions/tools/forum.ts`
   - `extensions/tools/reports.ts`
   - `extensions/tools/wiring.ts`
5. Add tests around extracted pure helpers before expanding analysis behavior.

Avoid mixing mechanical refactors with feature changes. Prefer PRs such as:

```text
refactor: extract figure helpers
refactor: split agent tools
feat: add coupling evidence bundle
```
