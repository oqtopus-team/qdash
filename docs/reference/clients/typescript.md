# TypeScript Client and SDK

Use `@oqtopus-team/qdash-sdk` for API access, calibrations, workflows, and dashboards.
It includes its own Fern-generated client. Existing `@oqtopus-team/qdash-client` applications
remain supported independently. Both require Node.js 20 or later.

## Installation

```bash
npm install @oqtopus-team/qdash-sdk
# For existing client applications:
npm install @oqtopus-team/qdash-client
```

Stable versions follow QDash releases. Append `@beta` for a prerelease.

## Connect to a Deployment

<a id="configuration"></a>

The SDK reads the same `config.toml` as Python, including `default_profile` and
top-level `[<name>]` tables. After installing the package, create the file with:

```bash
npx qdash config init --base-url http://localhost:5714/api --project-id your-project-id
```

This creates a `local` profile and refuses to overwrite an existing file. Both SDKs expose
`qdash config init` with the same [options](./python.md#initialize-a-configuration).
Follow the [profile setup](./python.md#connect-to-a-deployment) to fill in `api_token`, or
use `--api-token-env NAME` and set that variable in your Node.js or Bun process. For an existing `[profiles.local]` file, follow
[the TOML migration](./python.md#migrate-nested-toml-profiles).

```ts
import { QDash } from "@oqtopus-team/qdash-sdk";

const qdash = await QDash.fromProfile("local");
console.log((await qdash.api.chip.listChips()).chips);
```

Reuse `qdash` across operations; there is no connection to close. `QDash.fromProfile()` uses
`default_profile`, then `"default"`. An explicit name takes precedence. For an explicit file,
use `QDash.fromProfile("local", "/path/to/config.toml")`. The file uses snake_case keys;
JavaScript configuration uses camelCase:

```ts
const qdash = new QDash({
  baseUrl: "http://localhost:5714/api",
  apiToken: process.env.QDASH_API_TOKEN,
  projectId: "your-project-id",
  timeoutSec: 30,
});
```

Alternatively, `QDash.fromEnv()` reads `QDASH_BASE_URL`, `QDASH_API_TOKEN`, and
`QDASH_PROJECT_ID`, plus the [shared environment settings](./python.md#environment-variables).
Legacy worker and retry-backoff settings do not apply to the SDK.

INI profiles are deprecated in the SDK and emit `DeprecationWarning` with code
`QDASH_SDK_INI_CONFIG`. The SDK reads INI only when the default TOML file is absent or an
explicit `.ini` path is given. It never merges files or falls back after a TOML error.
Use the [INI migration procedure](./python.md#migrate-an-ini-profile); both SDKs use the same
TOML keys and profile selection rules.

`qdash.withProject(projectId)` returns a new scoped session without changing the original.
Configuration is a frozen snapshot. `proxy` or `verifyTls: false` requires a custom `fetch`
passed as the second constructor argument, such as `new QDash(config, { fetch: customFetch })`.
Construction fails if no custom fetch is supplied. The caller must ensure that the supplied
fetch implements the requested proxy or TLS policy; the SDK cannot verify that behavior.

An empty chip array indicates a successful connection to a project with no chips. Before
calibration examples, [create a chip and run its first calibration](../../user-guide/first-calibration.md).

For a host that supplies its own INI file, use `QDashConfig.fromIniFile(path, profile)`.
It reads the named file directly, including paths without a filename extension.

### Existing Client Applications

`@oqtopus-team/qdash-client` continues to use `config.ini` without this deprecation.
Its `QDashConfig.fromEnv().save("local")` writes INI with owner-only permissions;
`QDashClient.fromProfile("local")` reads it. Keep INI profiles for those applications.
The high-level client methods below are unchanged.

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

## Summarize Task Results

Use the SDK to count results across pages without writing a pagination script:

```ts
import { QDash } from "@oqtopus-team/qdash-sdk";

const qdash = await QDash.fromProfile("local");
const summary = await qdash.taskResults.summarize({
  chipId: "16Qv1",
  startFrom: "2026-11-19T00:00:00Z",
  startTo: "2026-11-26T00:00:00Z",
  timezone: "Asia/Tokyo",
  maxRows: 1000,
});
console.log(summary.total, summary.statusCounts);
if (!summary.complete) console.warn(summary.diagnostics);
console.log(summary.aggregates);
```

Replace the chip and time range with your own. `aggregates` counts distinct rows read by exact
stored status, task, and start day, plus distinct executions. `read.rows` is the number counted.
`total` and `statusCounts` come from the first page. `total` includes every filter;
`statusCounts` excludes the `status` filter and combines empty statuses with `"unknown"`.
Aggregates preserve empty statuses as `""`.

The default limit is 1000 rows; `maxRows` accepts 1–5000. `pageSize` accepts 1–100 (default 100),
and the requested row limit must fit within 50 pages. Filters also accept `taskName`, `qid`,
`executionId`, `username`, `status`, and `messageContains` (case-insensitive literal substring).
Days default to UTC; unreadable timestamps contribute to `aggregates.undated`.

Time bounds accept `YYYY-MM-DDTHH:MM[:SS[.ffffff]]`, optionally followed by `Z`, `±HH:MM`,
or `±HHMM`. Missing offsets mean UTC. Invalid dates and reversed ranges fail before any request.
Returned `filters` contain normalized bounds with explicit offsets. Row-time checks use
millisecond precision, matching database timestamps.
With a time bound, missing or unreadable row timestamps produce `row_start_unreadable`; rows
outside the inclusive bounds produce `row_outside_filters`. Both make `complete` false.

Check `complete` before presenting aggregates as covering the full result set. It is false for
truncation, duplicate rows, changing totals, or inconsistent results; inspect `diagnostics` and
narrow the range or retry as appropriate. Even a complete read is not a snapshot: concurrent
changes can escape offset-page checks. A malformed page or failed request rejects the call.

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
const page = await qdash.api.taskResult.listTaskResults({ chip_id: "64Qv3", qid: "6", limit: 1 });
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

## Define a Calibration

`@oqtopus-team/qdash-sdk/calibration` exports pure builders without authentication, HTTP,
or Node.js runtime imports. The package root exports the same builders.

| Python `qdash.calibration` | TypeScript builder |
| --- | --- |
| `QubitTargets`, `MuxTargets`, `CouplingTargets` | `qubitTargets`, `muxTargets`, `couplingTargets` |
| `TaskCall` | `taskCall` |
| `ConfigureAll`, `BringUp` | `configureAll`, `bringUp` |
| `OneQubitCheck`, `OneQubitFineTune`, `CustomOneQubit` | `oneQubitCheck`, `oneQubitFineTune`, `customOneQubit` |
| `FilterByStatus`, `FilterByMetric` | `filterByStatus`, `filterByMetric` |
| `GenerateCRSchedule`, `TwoQubitCalibration`, `CustomTwoQubit` | `generateCRSchedule`, `twoQubitCalibration`, `customTwoQubit` |
| `pipeline_spec`, `sweep` | `calibrationSpec`, `sweep` |

Step and task fields use snake_case. `taskCall` accepts either a name and fields or one object
containing `name`. Builders omit absent and `undefined` fields, preserve explicitly supplied
valid defaults and `null`, and omit empty target exclusions. Valid typed inputs serialize like
Python; TypeScript does not reproduce Pydantic's coercion of strings to numbers.

Builders reject invalid local fields with `TypeError` or `RangeError`, including unknown fields,
duplicate targets, and invalid execution modes. Existing builders now reject these invalid inputs
before a server request. Chip, task-catalog, and cross-step checks still require server validation.
`calibrationSpec` assembles its inputs without validating their contents.

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
and leaves the run active. Sleeps are capped at the remaining budget; no subsequent read
starts at or after the deadline. A read already in flight is not cancelled and remains subject
to its request timeout and retries. A zero timeout makes one initial read.
`get()` reads current status without waiting.

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
only; the workflow source stays on the server. The TypeScript handle polls the returned
execution ID. When that execution includes pipeline progress, it uses the pipeline status.
Otherwise it reports the execution’s own status. For a saved workflow that starts several
executions, use `workflowRun.response.flow_run_url` to verify the final workflow state in Prefect.

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

The SDK exposes every generated resource through `qdash.api`. Request and response fields
retain the API's snake_case spelling:

```ts
const chips = await qdash.api.chip.listChips();
const execution = await qdash.api.execution.getExecution({ execution_id: "your-execution-id" });
```

Pass optional list filters as arrays. For example, `status: ["active", "waiting_for_human"]`
on `qdash.api.agentSession.listAgentSessions` sends one query key per status.
When upgrading code that passes `null` for a session, qubit, or provenance list filter,
omit the field or use `undefined`.

These calls share the session's authentication and project header, disable retries by default,
and throw generated `ApiError` or `ApiTimeoutError`. SDK helpers translate failures to
`QDashApiError` subclasses: 409 becomes `QDashConflictError`, and 5xx responses remain
`QDashApiError`. Helper GETs retry transient statuses, connection failures, and timeouts up to
`readAttempts`; caller cancellation is not retried. Writes are sent once. Do not opt into
retries for execution writes without reconciling their effects.

Use `qdash.read(options => qdash.api.chip.listChips(options))` to apply the SDK’s read
retry and error handling to a generated read. Use `qdash.send(callback)` for a write and
forward its options to the generated method so the write is sent once. Both accept
`{ signal }` as a second argument for cancellation.

For a read that needs the raw HTTP response, `qdash.fetch(path, options)` accepts
a path relative to the API and returns a successful `Response`. Array entries in
`options.query` become repeated keys. Only GET and HEAD are retried. When implementing a
write into an existing calibration session, `qdash.preflightCalibrationSession(id, chipId)`
checks the owner’s session list before dispatch.

With username/password authentication, a resource's 401 invalidates the login used by that
request. The failed request is not replayed; the next call signs in again. Scoped sessions share
this state, and a late 401 cannot invalidate a newer sign-in. Static API tokens are unchanged.

With `calibrationSessionId`, pipeline execution first searches your sessions on the target
chip without changing their state. It checks up to 10,100 sessions, including closed sessions
for idempotent replay. If that check fails, `QDashPreflightError` means no launch request was
sent; its `cause` preserves a failed API read. Check the session, credentials and API availability.

`QDashResultUnknownError` means a dispatch response did not confirm the requested run
recording, or a successful HTTP response could not be read as a JSON object. The latter also
applies without recording options. It extends `QDashApiError` and exposes `executionId` when available. The operation
may have started: inspect that execution before deciding what to do; do not launch again
with a new key.

Import generated types through the `QDashApi` namespace from `@oqtopus-team/qdash-sdk`. Existing client users can continue
using `client.api.listChips()` and the client's `/models` and `/openapi` exports.

## Follow an Existing Run

```ts
const result = await qdash.run("your-execution-id").wait({ timeoutSeconds: 600 });
console.log(result.status);
```

Creating the handle dispatches no work. Waiting follows the whole pipeline; a timeout leaves
it running on the server.
