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
To expose a new pi-qdash tool in Copilot, add its reviewed name to the appropriate
read or write list in `agent-runtime/src/allowed-tools.ts` and update the runtime
allowlist checks in `agent-runtime/test/bundled-extensions.test.mjs`. Standalone pi
users can load the extension without this runtime list.

Figure tools return PNGs as image content so the model can inspect the curve;
Plotly JSON stays text. `qdash_build_qcal_evidence` keeps fitted outputs out of
the evaluation context by default while retaining them in structured details.
This lets pi-qcaleval judge the figure without reading the answer from a fit.

Timeseries comparison can combine QDash results with local CSV files. The
`/qdash-investigation-setup` preset stays in the pi session, outside the global
profile and chip context, so a local path does not carry into another project.
The extension never uploads CSV inputs, and its correlation and shared-period
results do not establish causality.

Pipeline execution is separate from agent candidate approval. A valid
`qdash_plan_pipeline` result precedes confirmation-gated `qdash_run_pipeline`;
the latter persists completed task parameters directly. Do not use it to retry
a failed agent action because that would bypass the candidate gate.

When adding a tool or command, update the [pi-qdash reference](../../reference/pi-qdash.md)
and add focused tests under `packages/pi-qdash/tests/`. Keep pure extraction helpers
separate from API calls so tests can exercise them without a live QDash deployment.

## pi-qcaleval

`packages/pi-qcaleval/extensions/qcaleval.ts` owns model selection, question templates,
request construction, and answer parsing. It has no QDash client dependency.
The host supplies task knowledge, figures, and labeled examples; the planner keeps
the conversation. The [pi-qcaleval reference](../../reference/pi-qcaleval.md) defines
the tool contract and standalone model configuration.

For standalone pi use, declare the evaluation model in pi's `models.json` with
its base URL and credential reference:

```json
{
  "providers": {
    "vllm": {
      "baseUrl": "https://llm.example/v1",
      "api": "openai-completions",
      "apiKey": "$VLLM_API_KEY",
      "models": [{ "id": "nvidia/Ising-Calibration-1.5-31B-NVFP4", "contextWindow": 16384, "maxTokens": 2048, "input": ["text", "image"] }]
    }
  }
}
```

pi-qcaleval sends each selected question as a separate single-turn request and
retries a failed call once. The requests run concurrently. Size the model
context for the figures and examples; set temperature to 0 for repeatable answers.

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
