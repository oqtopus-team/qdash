# QDash TypeScript Client

`@oqtopus-team/qdash-client` provides typed QDash API access for Node.js applications, extensions, and agent integrations.

## Installation

Install the package from npm. Node.js 20 or later is required.

```bash
npm install @oqtopus-team/qdash-client
```

Each QDash release tag `vX.Y.Z` publishes the client as `X.Y.Z` under the `latest` dist-tag, the same version as the [Python client](./python.md). Changes to either client, the API schema, the pi packages, root dependencies, or the release workflows on `develop` publish a prerelease under the `beta` dist-tag, versioned as the next QDash patch with a `-beta.<build>` suffix, where `<build>` counts the first-parent commits on `develop` (for example `1.10.3-beta.1278`). One release run computes this version once and publishes it to npm and, in PEP 440 spelling (`1.10.3b1278`), to PyPI. The two registries publish in sequence, not atomically: the PyPI release follows the npm release and can be missing until a failed PyPI run is retried. Use the beta to build against endpoints that are merged but not yet released, and switch back to `latest` once the release is tagged.

```bash
npm install @oqtopus-team/qdash-client@beta
```

`@oqtopus-team/qdash-sdk` and the pi packages release with the same QDash version; the SDK
takes the client's exact version and pins that client, and pi-qdash pins the client and SDK
built in the same run. Earlier client versions under the `pi` dist-tag came from
the former independent pi-qdash releases, which no longer exist. See
[Pi packages](../../developer-guide/copilot/packages.md) for local development
and release ordering.

## Connect to a Deployment

<a id="configuration"></a>

The clients share `QDASH_*` variables and named profiles. See
[Connect to a Deployment](./python.md#connect-to-a-deployment) for credentials, project IDs,
profile paths, and settings.

```ts
import { QDashClient } from "@oqtopus-team/qdash-client";

const fromEnvironment = QDashClient.fromEnv();
const fromProfile = await QDashClient.fromProfile("prod");
```

The required environment variable is `QDASH_BASE_URL`. API token, project, and Cloudflare Access authentication use `QDASH_API_TOKEN`, `QDASH_PROJECT_ID`, `QDASH_CF_ACCESS_CLIENT_ID`, and `QDASH_CF_ACCESS_CLIENT_SECRET`.

## High-Level Client

Use high-level methods for common data access and agent-calibration workflows.

```ts
const client = await QDashClient.fromProfile("prod");
const chip = await client.getDefaultChip();
const metrics = await client.getChipMetrics(chip.chip_id);

console.log(metrics.qubit_metrics);
```

The client provides polling helpers for QDash executions, agent action dispatch, execution linkage, and candidate application.

### List a Chip's Executions

`listExecutions({ chipId, skip, limit, date, timezone })` returns one page of a chip's executions as `{ executions, total }`. `chipId` is required; `limit` is an integer from 1 to 100 and `skip` an integer of 0 or more; `date` is one start day as `YYYYMMDD` in `timezone` (default UTC). `timezone` must be a non-empty string; the API checks that it names an IANA time zone. The API has no flow or status filter, so filter the returned rows instead. A missing or blank `chipId`, an invalid value, or any other option, including `flowName` or `status`, throws `QDashValidationError` before any request. `executionListProblems(options)` returns the same problems for every option except `chipId` as a list of messages, for a caller that checks its input before resolving the chip.

### Read a Target's Task History

`getQubitTaskHistory({ chipId, qid, task })` and `getCouplingTaskHistory({ chipId, couplingId, task })` return every result of one task for one target, newest first, as `{ name, data }` with `data` keyed by task ID. The routes have no date or paging filter: a missing option, a `date`, or any other option throws `QDashValidationError` before any request. For one period, use `listTaskResults` with `qid`, `taskName`, `startFrom` and `startTo`. A body without a string `name` and a `data` object of objects throws `QDashApiError`.

### Read Task Results in Pages

`listTaskResults` returns one page, newest first, as `{ items, total, skip, limit, status_counts }`. `limit` is an integer from 1 to 100 and `skip` an integer of 0 or more; other values throw `QDashValidationError` before any request instead of returning a smaller page. Filters use the API's names: `startFrom` and `startTo` bound the task start time, and `qid` matches one stored qubit or coupling ID exactly (`"6"`, `"6-7"`).

`collectTaskResults` reads up to `maxItems` rows (at most 10,000) in pages of `pageSize` (default and maximum 100), with the same filters on every page:

```ts
const { items, total, truncated } = await client.collectTaskResults({
  chipId: chip.chip_id,
  qid: "6",
  maxItems: 200,
});
```

It reads at most `Math.ceil(maxItems / pageSize)` pages and stops earlier at `maxItems`, at the last matching row, or at a short page. It sets `truncated` when the last response reports remaining rows or when duplicates prevent confirming a complete read. Duplicate rows can leave fewer than `maxItems` results even when more rows exist. A failed page, a malformed response, or an aborted `signal` rejects the whole call. Pages are offsets, not a snapshot, so rows are deduplicated by `task_id`. The SDK's `qdash.client` is the same client.

## Compare a Target's Latest Results

`qdash.taskResults.compareLatest({ chipId, qid, limit })` in the `@oqtopus-team/qdash-sdk` package (see [Run a Calibration](#run-a-calibration) for installation) compares the two newest results of each task name for one qubit or coupling:

```ts
const comparison = await qdash.taskResults.compareLatest({ chipId: "64Qv3", qid: "6", limit: 20 });
for (const item of comparison.compared) {
  if (item.status === "compared") console.log(item.task, item.changes);
  else console.log(item.task, "unavailable:", item.error);
}
console.log(comparison.insufficient); // [{ task, results: 1 }]
```

It reads the newest `limit` rows (an integer from 2 to 100, default 20) of `listTaskResults({ chipId, qid })`; `qid` is the exact stored qubit or coupling ID. List rows carry no output parameters, so for each task name with at least two rows it reads both details with `getTaskResult`: the newest row is `after`, the next is `before`. `changes` maps each output parameter whose `value` differs to `{ before, after }`; object key order is ignored, array order is not, and a parameter missing on one side is `undefined` there. A detail that fails, has no `output_parameters` object, or names another task ID, task name or `qid` makes the task `unavailable` with `changes: null` and an `error`, never unchanged. A task with one row is listed in `insufficient`, and `rows` gives `{ read, total }`. Invalid or unknown options throw `QDashValidationError` before any request.

## Run a Calibration

The separate `@oqtopus-team/qdash-sdk` package validates and starts calibrations and registered
workflows, with calls modelled on the [Python SDK](./python.md#run-a-calibration). It is built on
this client, which stays the API for every other route, and installs the client of the same
release:

```bash
npm install @oqtopus-team/qdash-sdk
```

This calibration runs `Configure`, `CheckT1` and `CheckT2Echo` on qubits 0 and 1 with the
sweeps of the `coherence_check` template:

```ts
import { QDash, customOneQubit, qubitTargets, sweep } from "@oqtopus-team/qdash-sdk";

const qdash = QDash.fromEnv(); // or new QDash(client, { projectId })
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

Both calls send the same spec version 2 object; the sweep is a declaration that the worker
expands, not a list of points (the exponents are rounded here):

```json
{
  "spec_version": 2,
  "targets": { "qids": ["0", "1"] },
  "steps": [{
    "type": "CustomOneQubit",
    "step_name": "coherence",
    "tasks": [
      { "name": "Configure" },
      { "name": "CheckT1", "run": { "time_range": { "value": [2.477, 5.699, 51], "value_type": "np.logspace" } } },
      { "name": "CheckT2Echo", "run": { "time_range": { "value": [2.477, 5.699, 51], "value_type": "np.logspace" } } }
    ]
  }],
  "default_run_parameters": { "readout_duration": 1024, "interval": 262144 }
}
```

| Call | Result |
| --- | --- |
| `QDash.fromEnv()`, `await QDash.fromProfile(...)`, `new QDash(client)` | A session over one `QDashClient`; nothing is sent and nothing needs closing |
| `qdash.chip(chipId)` | A `Chip` bound to the session's client, project and chip; nothing is sent |
| `chip.validateCalibration(targets, steps, options)` | `ValidatePipelineResponse`; problems are data, nothing is dispatched |
| `chip.calibrate(targets, steps, options)` | `CalibrationRun` once dispatched; `QDashValidationError` (422) for a calibration with problems |
| `run.wait({ timeoutSeconds: 3600, pollIntervalSeconds: 5 })` | `RunResult` with `executionId`, `status` and the raw `detail` once the whole run ends; `QDashTimeoutError` otherwise, and the run keeps going |
| `run.get()` | `RunResult` for the current state; `QDashNotFoundError` before the execution exists |
| `qdash.pipelines.catalog()`, `validate(spec, { chipId })`, `execute(spec, { chipId })` | The same routes for a whole spec, typed or a stored JSON object sent unchanged; `execute` returns a `PipelineRun` whose `wait()` returns the raw detail |

`options` takes `name`, `defaultRunParameters`, `tags` and `backendName`; the server's defaults
apply to each one left out. Targets, steps and task calls are the generated types
(`PipelineTargets`, `CustomOneQubitStep`, `TaskCall` and the other step types), so an object
literal in the spec's snake_case form works anywhere a helper does. `calibrate` does not
validate first; the server validates again before dispatch. `result.status` is the whole run's,
`detail.pipeline.status`, or `detail.status` when the server reports no pipeline progress, so a
run whose first step completed and whose later step failed reports `failed`. A failed or
cancelled run is returned, not thrown, and a 404 while the run is being created is polled again.
`projectId` scopes the session without changing the given client's configuration. Without a
project in the session or the client's configuration, requests carry no `X-Project-Id` and
QDash applies the user's default project, as for every client call; the Python SDK instead
refuses to run without a project. The SDK's error classes are the client's own, so
`instanceof QDashNotFoundError` works with either import.

Registered workflows, saved from the UI or with `saveFlow`, run the code stored in QDash:

```ts
for (const summary of await qdash.workflows.list()) console.log(summary.name, summary.chip_id);

const workflow = await qdash.workflows.get("coherence_check");
const workflowRun = await workflow.run({ parameters: { qids: ["0", "1"] } }); // measures
console.log((await workflowRun.wait()).status);
```

`parameters` override the saved `default_parameters` for this run only, and `{}` is sent when
they are left out. A name other than letters, digits and underscores throws `TypeError` before
any request.

How the SDK is built: [TypeScript SDK](../../developer-guide/architecture/typescript-sdk.md).

## Save Metric Scripts and Dashboards

`qdash.scripts` and `qdash.dashboards` save metric scripts and dashboards with the same
behavior as the [Python SDK](./python.md#save-metric-scripts-and-dashboards):

```ts
import { Dashboard, QDash, Script } from "@oqtopus-team/qdash-sdk";

const qdash = QDash.fromEnv();
const script = await qdash.scripts.create(await Script.fromFile("zx90_median.py", { visibility: "project" }));
const board = new Dashboard({ name: "ZX90 health", visibility: "project", chipId: "64Qv3" });
board.addMetric(script.metric("zx90_median"), { period: 14, params: { min_samples: 3 } });
const saved = await qdash.dashboards.create(board);

const current = await qdash.dashboards.get(saved.dashboardId);
const edited = current.edit();
edited.addMarkdown("Reviewed weekly.");
await qdash.dashboards.update(current, edited); // 409 when someone saved since `current`
```

`script.metric(id)` throws `MetricScriptError` when the saved revision is invalid or does not
declare the metric.

## Generated API

The complete API is generated by Orval from the QDash OpenAPI document. It is available through `client.api` and uses the same authentication, timeout, retry, and error handling as the high-level methods.

```ts
const chips = await client.api.listChips();
const posts = await client.api.listForumPosts({ limit: 20 });
```

Generated models and operation result types are exported from `@oqtopus-team/qdash-client/models` and `@oqtopus-team/qdash-client/openapi`. Application code should prefer the package root exports unless it needs a generated endpoint-specific type.
