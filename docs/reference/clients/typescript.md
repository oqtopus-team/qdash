# TypeScript Client

Use `@oqtopus-team/qdash-client` for API access and `@oqtopus-team/qdash-sdk` for calibrations.
Both require Node.js 20 or later.

## Installation

```bash
npm install @oqtopus-team/qdash-client
# Includes the matching client:
npm install @oqtopus-team/qdash-sdk
```

Stable versions follow QDash releases. Append `@beta` for a prerelease.

## Connect to a Deployment

<a id="configuration"></a>

Copy your token and project ID from **Settings → API Token**. Set `QDASH_BASE_URL` to the
deployment URL ending in `/api`, plus `QDASH_API_TOKEN` and `QDASH_PROJECT_ID` in your environment.
Save a profile with the installed client (no Python required):

```ts
import { QDashConfig } from "@oqtopus-team/qdash-client";

await QDashConfig.fromEnv().save("local");
```

Profiles use `$XDG_CONFIG_HOME/qdash/config.ini`, or `~/.config/qdash/config.ini`, shared with the
Python client and pi-qdash. `save()` writes owner-only permissions. Connect with that profile:

```ts
import { QDashClient } from "@oqtopus-team/qdash-client";

const client = await QDashClient.fromProfile("local"); // or QDashClient.fromEnv()
console.log((await client.listChips()).chips);
```

An empty array is a successful connection to a project with no chips. Before calibration examples,
[create a chip and run its first calibration](../../user-guide/first-calibration.md).

<a id="list-a-chip-s-executions"></a>
<a id="read-a-target-s-task-history"></a>
<a id="read-task-results-in-pages"></a>

## High-Level Client

| Read | Contract |
| --- | --- |
| `listExecutions({ chipId, skip, limit, date, timezone })` | `{ executions, total }`; chip required; limit 1–100; date `YYYYMMDD`; timezone defaults to UTC; no flow/status filter |
| `getQubitTaskHistory({ chipId, qid, task })` | All task results, newest first, as `{ name, data }`; no date or paging filters |
| `getCouplingTaskHistory({ chipId, couplingId, task })` | Same history contract for a directed coupling |
| `listTaskResults({ chipId, qid, startFrom, startTo, skip, limit })` | `{ items, total, skip, limit, status_counts }`; newest first; limit 1–100; `qid` is an exact stored target ID |
| `collectTaskResults({ chipId, qid, maxItems, pageSize })` | `{ items, total, truncated }`; at most 10,000 rows, page size at most 100 |

Invalid options fail before a request. Collection pages are not a snapshot; rows are deduplicated
by task ID. Check `truncated` and do not treat a failed page as a complete read.

## Compare a Target's Latest Results

```ts
import { QDash } from "@oqtopus-team/qdash-sdk";

const qdash = await QDash.fromProfile("local");
const comparison = await qdash.taskResults.compareLatest({ chipId: "64Qv3", qid: "6", limit: 20 });
```

This SDK call compares output values in the two newest results of each task within the selected
2–100 rows (default 20). `compared` contains changes or an `unavailable` error; `insufficient`
lists tasks with only one result. A failed detail read never means unchanged.
Replace `64Qv3` and `6` with a chip and target in your project.

## Read a Result with Context

`qdash.taskResults.evidence(taskId, { cooldownId? })` joins a saved result with its execution,
current qubit or coupling state, and an optional named cooldown. It performs only reads in the
session's project. Use a task ID from `listTaskResults`:

```ts
import { QDash } from "@oqtopus-team/qdash-sdk";

const qdash = await QDash.fromProfile("local");
const page = await qdash.client.listTaskResults({ chipId: "64Qv3", qid: "6", limit: 1 });
if (!page.items[0]) throw new Error("No saved results for this target");
const evidence = await qdash.taskResults.evidence(page.items[0].task_id);
console.log(evidence.result.output_parameters);
if (evidence.target.status === "ok") console.log(evidence.target.value.outputs);
else console.log(evidence.target);
```

Replace the chip and target with your own. A failed result read rejects the call. Each of
`execution`, `target`, and `cooldown` uses the exported `TaskResultContext<T>` union:

| Status | Fields |
| --- | --- |
| `ok` | `value` contains the context |
| `failed` | `error` and, for HTTP errors, `statusCode` |
| `not_applicable` | `reason` explains the missing execution ID, target, or chip |
| `not_associated` | `reason` explains the unavailable cooldown association |

Target outputs are current stored values, not a historical snapshot. `fromThisResult` is
`true` or `false` when a stored entry names a task, otherwise `null`.
The API does not expose the result's cooldown ID, so no cooldown is inferred. Pass a known
`cooldownId` to check its chip membership and time compatibility; these checks do not establish
that the result belongs to that cooldown. Inspect failed or missing parts before drawing a conclusion.

## Run a Calibration

This example measures qubits 0 and 1. Choose targets and settings suitable for your hardware;
spec validation is not a physical safety check.

```ts
import { QDash, customOneQubit, qubitTargets, sweep } from "@oqtopus-team/qdash-sdk";

const qdash = await QDash.fromProfile("local");
const chip = qdash.chip("64Qv3");

const timeRange = sweep.logspace(Math.log10(300), Math.log10(500_000), 51);
const targets = qubitTargets(["0", "1"]);
const steps = [
  customOneQubit({
    step_name: "coherence",
    tasks: [
      { name: "Configure" },
      { name: "CheckT1", run: { time_range: timeRange } },
      { name: "CheckT2Echo", run: { time_range: timeRange } },
    ],
  }),
];
const defaultRunParameters = { readout_duration: 1024, interval: 262_144 };

const check = await chip.validateCalibration(targets, steps, { defaultRunParameters });
if (!check.valid) throw new Error(check.problems?.map((p) => `${p.path}: ${p.message}`).join("\n"));

const run = await chip.calibrate(targets, steps, { defaultRunParameters }); // measures
console.log(run.executionId);
const result = await run.wait({ timeoutSeconds: 3600 });
console.log(result.status);
```

`validateCalibration()` dispatches nothing; `calibrate()` starts the run. `wait()` returns the
whole run's status, including failure or cancellation. A timeout throws `QDashTimeoutError`
and leaves the run active. `get()` reads current status without waiting.

For stored specs, use `qdash.pipelines.catalog()`, `validate(spec, { chipId })`, and
`execute(spec, { chipId })`. The returned pipeline run's `wait()` returns raw execution detail.
See [pipeline specs](../../developer-guide/workflow/calibration-pipeline.md).

Without a configured project, the TypeScript SDK uses the server's default project; the Python
SDK instead requires an explicit project before running.

## Run a Registered Workflow

First [save a workflow](../../user-guide/creating-workflows.md); replace `coherence_check` with
its **Flow Name**. Reuse the `qdash` session above and choose targets supported by the workflow.

```ts
const workflow = await qdash.workflows.get("coherence_check");
const workflowRun = await workflow.run({ parameters: { qids: ["0", "1"] } });
console.log((await workflowRun.wait()).status);
```

`qdash.workflows.list()` lists saved workflows. Parameters override saved defaults for this run
only; the workflow source stays on the server.

## Save Metric Scripts and Dashboards

```ts
import { Dashboard, QDash } from "@oqtopus-team/qdash-sdk";

const qdash = await QDash.fromProfile("local");
const script = await qdash.scripts.create(await qdash.scripts.template("zx90_median", { visibility: "project" }));
const board = new Dashboard({ name: "ZX90 health", visibility: "project", chipId: "64Qv3" });
board.addMetric(script.metric("zx90_median"), { period: 14, params: { min_samples: 3 } });
const saved = await qdash.dashboards.create(board);
```

This uses the built-in **Median ZX90 fidelity** template; no local file is needed.
Panels pin the saved revision. To edit a dashboard, get it, call
`edit()`, and pass both to `qdash.dashboards.update(current, edited)`. On HTTP 409, read it again.
See [metric scripts](../../user-guide/metric-scripts.md) for authoring.

## Generated API

Use `client.api` for any [OpenAPI](../openapi.md) operation without a high-level helper:

```ts
const chips = await client.api.listChips();
```

It shares authentication, timeouts, retries, and error handling with the high-level client.
Generated types are available from the package's `/models` and `/openapi` exports.
