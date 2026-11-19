# Pi Extension Design

The bundled pi extensions own tool execution and skills; the QDash runtime owns
session orchestration, tool exposure, and host context. See
[Pi Packages](./packages.md) for workspace setup and release procedures.

## pi-qdash

`packages/pi-qdash/extensions/qdash.ts` registers QDash tools, slash commands, and
TUI renderers. Shared helpers live under `extensions/lib/`; domain tool registration
lives under `extensions/tools/`, including `timeseries.ts`.

The investigation policy and tool routing guide that every host gives the model live in
`extensions/lib/qdash-guidance.ts`. The routing guide is the "Preferred tools" section of
`skills/qdash/SKILL.md`, limited to the tools the host offers. In pi CLI,
`extensions/lib/guidance-hook.ts` sets them as the `qdash_guidance` system prompt section before
each run, from the tools selected for that run. pi keeps its own prompt, `--system-prompt`,
`--append-system-prompt`, and context files around the section, and the section is replaced
rather than appended on later runs. The QDash runtime does not run this hook; it composes the
same policy and guide with its own chat rules in `agent-runtime/src/prompt.ts`. Keep display,
approval, and orchestration rules for one host out of `qdash-guidance.ts`.

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
To expose a new pi-qdash tool in Copilot, add its reviewed read name to
`ALLOWED_TOOL_NAMES` in `agent-runtime/src/allowed-tools.ts` and update the runtime
allowlist checks in `agent-runtime/test/bundled-extensions.test.mjs`. The write list
(`REVIEWED_WRITE_TOOL_NAMES`), the reads `codemode` scripts may call
(`NESTED_READ_TOOL_NAMES`), and the tools the model loads on demand
(`DEFERRED_TOOL_NAMES`) live in `extensions/lib/tool-policy.ts`, which both hosts enforce;
see [Code Mode and deferred tools](./architecture.md#code-mode-and-deferred-tools).
In pi CLI, `extensions/lib/script-policy.ts` applies them through pi's tool exposure and
`tool_call` and `tool_result` hooks. It trusts a QDash name in a script only while pi runs
pi-qdash's own registration (`extensions/lib/extension-identity.ts`), and it keeps the user's
`codemode` and `tool_search` selection across pi's session lifecycle
(`extensions/lib/tool-selection.ts`), as listed in the
[pi-qdash reference](../../reference/pi-qdash.md#scripts-and-deferred-tools). Standalone pi
users need no runtime allowlist.

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
the conversation. Both hosts fill them with `extensions/lib/qcal-hydration.ts` in pi-qdash:
the runtime in `agent-runtime/src/durable-tools.ts`, and pi CLI in
`extensions/lib/qcal-hydration-hook.ts` when pi-qdash is loaded next to pi-qcaleval. The [pi-qcaleval reference](../../reference/pi-qcaleval.md) defines
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

To run pi with the Copilot chat model instead of your own pi model settings, use
`task pi-local`; arguments after `--` go to pi:

```bash
task pi-local -- -p "Which chip is the default chip?"
# A checkout without its own .env, such as a worktree:
task pi-local -- --env-file /path/to/qdash/.env
```

`agent-runtime/src/local-cli.ts` builds `models.json` from `config/copilot/chat.yaml`
and `evaluation.yaml`, or from the profile `QDASH_COPILOT_PROFILE` selects, with the
runtime's `buildModelsConfig`. It loads pi-qdash and starts the first `chat_models`
entry at the thinking level of its `reasoning_effort`. A first model whose endpoint is
unset stops the run instead of falling back to another model. `--model <provider/id>`
starts that model instead, whether or not the default resolves, and `--thinking <level>`
sets the level. The default's level applies to `--model` only when it names the same
`provider/id`. Pass these flags and their values as separate arguments, as pi reads them;
the launcher rejects `--model=<value>`.

The launcher parses `.env` as data, never as shell code, and takes from it only
`QDASH_COPILOT_PROFILE`, the config path overrides, and the endpoint, key, and
Cloudflare Access variables the models name. A variable already set in the shell
wins, even when empty. The parser reads one `NAME=value` per line with an optional
`export` prefix: single-quoted values are literal, double-quoted values accept the
`\n`, `\t`, `\r`, `\"`, `\\`, and `\$` escapes, and unquoted values drop a ` #` comment.
Unquoted and double-quoted values expand `$NAME`, `${NAME}`, `${NAME-default}`, and
`${NAME:-default}`, taking the shell's value before the file's. Other forms, multi-line
values, and text after a closing quote are not supported; the launcher skips such a
line and reports its line number. `models.json` stores keys as `$NAME` references, and pi state goes to the
ignored `.pi-local/agent/` (or `--agent-dir`), so `~/.pi/agent` is untouched.
QDash connection settings stay pi-qdash's own: set `QDASH_BASE_URL` with
`QDASH_API_TOKEN` in the shell, or use a profile in `~/.config/qdash/config.ini`.

pi reads a piped stdin to EOF before it writes its first event, even when the prompt is an
argument, so a caller that holds stdin open without writing, such as an agent's command tool,
would stall pi with no output. When stdin is a pipe or socket and the arguments already carry a
prompt, the launcher relays stdin and, if no byte arrives within 2 seconds, closes pi's stdin and
warns that the run starts without piped input. Input that starts within that window is passed to
EOF. Pass `--wait-stdin` to hand stdin to pi unchanged, for a producer that is slower to start;
a terminal, a file, `/dev/null`, `--mode rpc`, or a run whose only prompt is the piped input is
always handed over unchanged. The launcher forwards `SIGINT`, `SIGTERM`, and `SIGHUP` to pi, so
stopping it does not leave pi to run the prompt later.

Use `/reload` in pi after changing extensions or skills. Follow the repository
[pre-push procedure](../development-flow.md#before-pushing) before submitting changes.
