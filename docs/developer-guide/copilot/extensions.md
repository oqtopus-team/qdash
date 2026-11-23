# Pi Extension Design

The bundled pi extensions own tool execution and skills; the QDash runtime owns
session orchestration, tool exposure, and host context. See
[Pi Packages](./packages.md) for workspace setup and release procedures.

## Supported hosts

pi-qdash is the agent capability shared by two supported hosts: pi CLI, and the QDash
web application's **Agent** through the agent runtime. The hosts share capability, not
presentation, and their features differ; document a difference where the feature is
described instead of implying parity.

| Concern | Owner |
| --- | --- |
| QDash tools, skills, investigation and request policies, tool routing guide, and tool policy lists | pi-qdash, for both hosts |
| Presentation, sessions, the context a turn carries, orchestration, and which tools are exposed | Each host |

- **Permissions.** Both hosts apply the same rule: reads run directly, and a reviewed write
  runs only after the user approves that call in the host's own UI; no tool argument approves a
  write (`extensions/lib/write-approval.ts`). pi CLI asks in its dialog and refuses the write
  when it has no UI, as with `pi -p` (`extensions/lib/write-gate.ts`); the runtime shows an
  approval card and runs the approved call on a frozen copy of the arguments the user saw,
  passing the approval for that call id and tool in the extension context
  (`QDashWriteTools.runApproved` in `agent-runtime/src/durable-tools.ts`). The one exception is
  the session-granted writes `qdash_run_agent_session_step`, `qdash_request_agent_human`,
  `qdash_record_agent_decision`, and `qdash_commit_agent_session_update`
  (`SESSION_GRANTED_WRITE_TOOL_NAMES`): neither host asks. The step and request tools act in an
  agent session the user approved with `autonomy: auto` when it was created, a reviewed write;
  the update tool acts only when that approval also granted `parameter_updates`; the decision
  tool only appends to the audit of a session the user created. Each call re-reads the
  session and refuses anything outside it before QDash checks it again; see
  [The model-driven loop](./agentic-calibration.md#the-model-driven-loop).
- **Results.** A tool returns readable text in `content` and reusable structured data in
  `details` (`extensions/lib/results.ts`), so a host without a renderer for a result still
  shows its text.
- **Host context.** Context such as the open page or a task result comes from the host,
  not from pi-qdash; see [Page context and editor edits](./architecture.md#page-context-and-editor-edits)
  for the web application. The model each QDash agent record names also comes from the host,
  never from a tool argument: `ctx.model` in pi CLI and the conversation's model reference in
  the runtime (`extensions/lib/host-model.ts`); see
  [Experiment audit](./agentic-calibration.md#experiment-audit).
- **Verification.** A change to shared behavior is checked in both hosts, as described in
  [Verify a change](#verify-a-change). A feature or limit specific to one host, such as pi
  CLI slash commands or the web application's approval cards, is stated as such.

## pi-qdash

`packages/pi-qdash/extensions/qdash.ts` registers QDash tools, slash commands, and
TUI renderers. Shared helpers live under `extensions/lib/`; domain tool registration
lives under `extensions/tools/`, including `timeseries.ts`.

The investigation policy, request policy, and tool routing guide that every host gives the
model live in `extensions/lib/qdash-guidance.ts`. The request policy lets a plain request such as
"remeasure the T1 of Q0" select a skill by its description: it separates questions about stored
values from requests to measure, takes targets from context before asking, keeps plan-only
requests free of writes, and has a broad calibration ask once whether to run agentically or as a
reviewed workflow unless the request or conversation already says. That answer is a preference:
it neither approves a write nor lets a stopped path fall back to the other. It names no flows, tasks, or thresholds, and grants no write permission. The routing guide is the "Preferred tools" section of
`skills/qdash/SKILL.md`, limited to the tools the host offers. In pi CLI,
`extensions/lib/guidance-hook.ts` sets them as the `qdash_guidance` system prompt section before
each run, from the tools selected for that run. pi keeps its own prompt, `--system-prompt`,
`--append-system-prompt`, and context files around the section, and the section is replaced
rather than appended on later runs. The QDash runtime does not run this hook; it composes the
same policies and guide with its own chat rules in `agent-runtime/src/prompt.ts`. Keep display,
approval, and orchestration rules for one host out of `qdash-guidance.ts`.

`extensions/tools/metric-scripts.ts` adds the metric script and dashboard tools: the
`qdash_query` actions for scripts, templates, the data catalog and dashboards, the direct tools
`qdash_validate_metric_script` and `qdash_preview_metric_script` (they execute code on the QDash
server, so they are not script-callable reads), and the reviewed writes
`qdash_save_metric_script` and `qdash_save_dashboard`. All four direct tools are deferred.
The tools only reach the API and format its answers; the `qdash_metrics` API and the authoring
workflow live in `skills/qdash-metric-scripts/`. When the web application's metric script
editor is open, the runtime adds the editor's text to the prompt and offers
`propose_code_edit` for it, as it does for the Workflow editor and for a dashboard the
user may edit, where the proposal is the dashboard's draft as JSON; see
[Page context and editor edits](./architecture.md#page-context-and-editor-edits).

Keep API access through `@oqtopus-team/qdash-client`, redaction, rendering, and
mechanical evidence extraction in extensions. Keep calibration interpretation,
diagnosis recipes, thresholds, and runbooks in `packages/pi-qdash/skills/`.
For example, `extensions/lib/figure-analysis.ts` summarizes Plotly JSON;
`skills/qdash-two-qubit-calibration/` decides from that evidence which two-qubit step to rerun.
The experiment-flow skills (`qdash-chip-bringup`, `qdash-one-qubit-calibration`,
`qdash-two-qubit-calibration`, and `qdash-characterization`) compose the flow templates toward a
goal and leave task physics to task knowledge. `qdash-zx90-optimization` composes ordinary
pipelines into an adaptive search that the model drives only within active chat turns; no
QDash service runs or resumes it. The runtime's `read_skill` returns only a skill's
`SKILL.md`, so these skills keep their instructions in that file and retrieve templates and task
documentation through tools. Both hosts list each skill's description before the model loads it,
so a description states the goal it serves in the user's terms and the requests it does not
serve; `agent-runtime/test/bundled-extensions.test.mjs` checks that they
load and name only tools the runtime offers.

New tools are read-only by default. A write or operational call is added to
`REVIEWED_WRITE_TOOL_NAMES` and calls `requireWriteApproval` before it writes; it takes no
argument that approves it, so a model cannot approve its own write, and it is refused in a
session without a UI. The approval logic lives in `extensions/lib/write-approval.ts`, the pi
CLI gate in `extensions/lib/write-gate.ts`, and the review the user approves in
`extensions/lib/write-review.ts`; output redaction lives in `extensions/lib/results.ts`.

Every review shows the complete canonical arguments after a summary of the write
(`approvalReviewText`), and nothing in it is shortened. pi's `ctx.ui.confirm()` draws its message
in the input dock, which pi clips to the terminal without scrolling, so in the pi terminal UI
(`ctx.mode === "tui"`) `reviewWrite` opens a full-height overlay through `ctx.ui.custom()`
instead. The overlay sizes itself to the terminal's rows and scrolls with the arrow, Page Up, Page
Down, Home, and End keys. It accepts `y` only after its last line has been on screen, and `n`,
Escape, or pi's abort signal declines. A terminal too small to show the review refuses approval.
In pi RPC mode, which has no custom UI, the RPC client receives the complete text through
`confirm()` and is responsible for showing it. The QDash web Agent uses neither: it shows its
own approval card.

An approval covers one call's value, not an object reference. The pi CLI gate's `tool_call`
hook takes a canonical snapshot of the arguments (`canonicalArgs`: plain JSON data with sorted
keys), shows the session grant for `qdash_create_agent_session` and every argument of that
snapshot in the review, and waits with pi's abort signal. It records the snapshot for the call id and tool name only when the user
accepted, the turn was not aborted, and the arguments did not change while the dialog was open.
The tool's `requireWriteApproval` consumes the record once and runs only when its arguments
still equal it, so a later `tool_call` hook that changes nested arguments in place stops the
call. The gate forgets a record at `tool_execution_end`, which pi emits for a call that a later
hook blocked or an abort skipped, and forgets all of its records at `turn_end`, `agent_end`, and
`session_shutdown`. A tool's own dialog, used when neither the gate nor a host approved the
call, likewise refuses a call whose arguments changed or whose turn was aborted while it was
open. Arguments that are not plain
JSON data, such as a cycle, a class instance, or an accessor, are refused without a dialog.
`packages/pi-qdash/tests/write-approval.test.mjs`,
`packages/pi-qdash/tests/write-review.test.mjs`, which runs the review in pi-tui's
`TuiMainScreen`, and `agent-runtime/test/write-gate-lifecycle.test.mjs`, which drives a real pi
session in RPC and terminal modes, cover the lifecycle. Keep credentials out of fixtures and examples.
The runtime additionally controls which tools it exposes, as described in
[Copilot Architecture](./architecture.md#developing-a-pi-extension-against-the-runtime).
To expose a new pi-qdash tool in Copilot, add its reviewed read name to
`ALLOWED_TOOL_NAMES` in `agent-runtime/src/allowed-tools.ts` and update the runtime
allowlist checks in `agent-runtime/test/bundled-extensions.test.mjs`. The write lists
(`REVIEWED_WRITE_TOOL_NAMES`, and `SESSION_GRANTED_WRITE_TOOL_NAMES` for writes an approved
agent session covers), the reads `codemode` scripts may call (`NESTED_READ_TOOL_NAMES`), and
the tools the model loads on demand (`DEFERRED_TOOL_NAMES`) live in
`extensions/lib/tool-policy.ts`, which both hosts enforce;
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
a failed agent action because that would bypass the candidate gate. For the same
reason `qdash_run_pipeline` and `qdash_execute_flow` start nothing while one of the
user's own agent sessions waits for an expert on the same chip and targets
(`pausedSessionConflict` in `extensions/lib/agent-loop.ts`). When the session list cannot be
read, including a 404 or 405 from a QDash release without `GET /agent-sessions`, they start
nothing either: such a server can still hold paused sessions, and there is no flag to skip the
check. The guard reads one page of at most 100 paused sessions, newest first, so a full page
without an overlap also starts nothing: an older paused session could cover the targets. The check is in pi-qdash, not in QDash: a person running a flow from the web application
is not blocked.

The pipeline tools and `qdash_execute_flow` reach QDash through the
[TypeScript SDK](../architecture/typescript-sdk.md) package `@oqtopus-team/qdash-sdk`
(`qdash.pipelines` and `qdash.workflows.run`), which builds the requests, and
`qdash_compare_calibration` compares results with `qdash.taskResults.compareLatest`; other
tools use `@oqtopus-team/qdash-client` directly. A tool resolves the default chip and target
from its context and adapts its arguments; the SDK or client owns the comparison and the input
checks other callers also need. A profile without a project keeps
running on the server's default project. Confirmation, input checks, the 422 and
503 handling and the structured results stay in the tools. A run tool returns the execution ID as soon as QDash
accepts the run and never calls the SDK's `wait()`; `qdash_wait_execution` follows
the run when asked.

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
