# Pi Extension Design

The bundled pi extensions own tool execution and skills; the QDash runtime owns
session orchestration, tool exposure, and host context. See
[Pi Packages](./packages.md) for workspace setup and release procedures.

## pi-qdash

`packages/pi-qdash/extensions/qdash.ts` registers QDash tools, slash commands, and
TUI renderers. Shared helpers live under `extensions/lib/`; domain tool registration
lives under `extensions/tools/`, including `timeseries.ts`.

Keep API access through `@oqtopus-team/qdash-client`, redaction, rendering, and
mechanical evidence extraction in extensions. Keep calibration interpretation,
diagnosis recipes, thresholds, and runbooks in `packages/pi-qdash/skills/`.
For example, `extensions/lib/figure-analysis.ts` summarizes Plotly JSON;
`skills/qdash-two-qubit-calibration-diagnosis/` interprets calibration evidence.

New tools are read-only by default. Writes and operational calls must use the
existing approval gates, including explicit `confirmWrite: true` in non-interactive
runs. Shared gate logic lives in `extensions/lib/write-gate.ts`; output redaction
lives in `extensions/lib/results.ts`. Keep credentials out of fixtures and examples.
The runtime additionally controls which tools it exposes, as described in
[Copilot Architecture](./architecture.md#developing-a-pi-extension-against-the-runtime).

When adding a tool or command, update the [pi-qdash reference](../../reference/pi-qdash.md)
and add focused tests under `packages/pi-qdash/tests/`. Keep pure extraction helpers
separate from API calls so tests can exercise them without a live QDash deployment.

## pi-qcaleval

`packages/pi-qcaleval/extensions/qcaleval.ts` owns model selection, question templates,
request construction, and answer parsing. It has no QDash client dependency.
The host supplies task knowledge, figures, and labeled examples; the planner keeps
the conversation. The [pi-qcaleval reference](../../reference/pi-qcaleval.md) defines
the tool contract and standalone model configuration.

Update `packages/pi-qcaleval/tests/` when changing templates, model selection, or
parsed output. Changes to the host adapter also need runtime tests; see
[Calibration Evaluation](./evaluation.md) for the integration and record format.

## Verify a change

Run `task ci-pi-packages` for extension typechecks, tests, and release-script tests,
and `task ci-agent-runtime` for integration checks. Both build the workspace client
first. For interactive checks from the repository root, load the relevant package:

```bash
pi -e ./packages/pi-qdash
# Or test the standalone evaluator:
pi -e ./packages/pi-qcaleval
```

Use `/reload` in pi after changing extensions or skills. Follow the repository
[pre-push procedure](../development-flow.md#before-pushing) before submitting changes.
