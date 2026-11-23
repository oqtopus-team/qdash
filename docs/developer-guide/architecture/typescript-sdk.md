# TypeScript SDK

`@oqtopus-team/qdash-sdk` lets a TypeScript application validate or start a calibration on a chip,
run the workflows registered in a project, save metric scripts and dashboards, and compare a
target's latest task results, through the QDash API. It is a separate npm
package in `sdks/typescript/`, built on `@oqtopus-team/qdash-client`; the user-facing example is
in the [TypeScript Client reference](../../reference/clients/typescript.md#run-a-calibration).
Its calls are modelled on the [Python SDK](./python-sdk.md), with one difference in how a
missing project is handled, described below.

## Responsibility boundary

| Layer | Owns | Leaves to others |
| --- | --- | --- |
| `@oqtopus-team/qdash-client` (`QDashClient`) | Configuration and profiles, authentication, `X-Project-Id`, HTTP transport, retries, error classes, one method per route, generated types, `withProject`, `waitForExecution`, input checks that need no server data (such as `executionListProblems`) and response-shape checks of a route | Building request bodies from domain calls, operations over several routes |
| `@oqtopus-team/qdash-sdk` | The `QDash` session, `Chip`, `Workflows`, `Pipelines`, `TaskResults`, the target, step and sweep helpers, the run handles, the `Script` and `Dashboard` definitions and their saved handles, operations that combine several client calls, such as `compareLatest` | Transport, auth, retries, any check that needs server data |
| A host such as pi-qdash | Default chip and target from its context, tool argument schemas and their wording, approvals, rendering | Comparison and validation logic other SDK callers also need |
| API | Authentication, project authorization, the step and task catalog, preflight, dispatch | Anything on the caller's machine |

The client does not depend on the SDK and exports no SDK entry point. The SDK depends on the
client only, imports it as an external package and does not bundle it, so an application has
one client and the SDK's re-exported errors (`QDashApiError`, `QDashConfigError`,
`QDashNotFoundError`, `QDashTimeoutError` and the others) are the client's own classes.
`instanceof` works with either import.

## Calls and the client calls behind them

The SDK adds no transport, retries or caches; each call delegates to the client:

| SDK call | Client call |
| --- | --- |
| `qdash.pipelines.catalog`, `validate`, `execute` | `client.api.getCalibrationPipelineCatalog`, `validateCalibrationPipeline`, `executeCalibrationPipeline` |
| `chip.validateCalibration`, `chip.calibrate` | `qdash.pipelines.validate`, `qdash.pipelines.execute` with the spec `calibrationSpec` builds |
| `qdash.workflows.list`, `get`, `run` | `client.listFlows`, `getFlow`, `executeFlow` |
| `qdash.scripts.list`, `get`, `template`, `validate`, `create`, `update` | `client.listMetricScripts`, `getMetricScript`, `listMetricScriptTemplates`, `validateMetricScript`, `createMetricScript`, `updateMetricScript` |
| `qdash.dashboards.list`, `get`, `create`, `update` | `client.listDashboards`, `getDashboard` (also before an update by ID), `createDashboard`, `updateDashboard` |
| `run.wait()` | `client.waitForExecution` with `wholePipeline: true` and `notFoundAsPending: true` |
| `run.get()` | `client.getExecution` |
| `qdash.taskResults.compareLatest` | `client.listTaskResults`, then `client.getTaskResult` for the two newest rows of each task name, at most four tasks at a time |
| `new QDash(client, { projectId })` | `client.withProject`, a new client with the same transport options |

Targets, steps and task calls are the generated types from `ui/src/schemas/`, written in the
spec's snake_case JSON form, so the SDK has no second model of the spec. The helpers
`qubitTargets`, `muxTargets`, `customOneQubit` and `sweep` only fill in the target shape, the step
`type` and sweep declarations. Method options outside the spec, such as `defaultRunParameters`
and `backendName`, are camelCase. A session holds nothing to close, and creating it, a chip or a
workflow handle sends no request. A timeout throws `QDashTimeoutError` and leaves the run going.
`client.waitForExecution` keeps throwing `QDashNotFoundError` on a 404 unless it is called with
`notFoundAsPending: true`, so existing client callers see no change.

## Metric scripts and dashboards

`Script`, `Dashboard`, `SavedScript.metric` and `Dashboard.addMetric` follow the
[Python SDK's semantics](./python-sdk.md#metric-scripts-and-dashboards) with camelCase names:
`Script.fromFile(path, { visibility })` reads text, a save binds a `SavedScript` to the revision
it produced, `metric(id)` throws `MetricScriptError` for an invalid revision or unknown metric,
and `qdash.dashboards.update(target, board)` sends `expected_version`. Panels and their
`MetricScriptPanelConfig` are the generated types in their snake_case JSON form. A series metric
(`ScriptMetric.result === "series"`) gets a `timeseries` panel and needs `targets`, as in Python:
`board.addMetric(trend, { period: 28, targets: ["0>1", "1>0"] })`. A scalar panel's config
omits `targets`, as in Python.

```ts
import { Dashboard, QDash, Script } from "@oqtopus-team/qdash-sdk";

const qdash = QDash.fromEnv();
const script = await qdash.scripts.create(await Script.fromFile("zx90_median.py", { visibility: "project" }));
const board = new Dashboard({ name: "ZX90 health", visibility: "project", chipId: "64Qv3" });
board.addMetric(script.metric("zx90_median"), { period: 14, params: { min_samples: 3 } });
const saved = await qdash.dashboards.create(board);
```

pi-qdash's `qdash_save_metric_script` saves through `qdash.scripts`. `qdash_save_dashboard`
keeps calling the client, because it updates only the fields given and the SDK replaces the whole
definition; it forwards an optional `expectedVersion`.

## Project scope

`projectId` scopes a session through `client.withProject`; the given client and its
configuration are not changed. Without `projectId`, the session uses the client as it is. When
the client has no project either, requests carry no `X-Project-Id` and QDash applies the user's
default project, as it does for every other client call; the server still authenticates the
user and authorizes the project. `chip.calibrate`, `qdash.pipelines.execute` and
`qdash.workflows.run` therefore dispatch without a configured project.

This keeps existing pi-qdash profiles that rely on the server's default project working. The
Python SDK is stricter: its run calls raise `QDashConfigError` without a project. The two SDKs
do not match on this point.

A workflow name other than letters, digits and underscores throws `TypeError` before any
request, as in the Python SDK.

`qdash.pipelines.execute(spec, target, recordIn)` takes an optional third argument,
`{ calibrationSessionId, idempotencyKey, decisionId? }`, that records the run in a calibration
session before it is launched; a retry with the same key returns the recorded run, and
`decisionId` names the session's decision the run carries out. An empty session ID or key throws
`TypeError` before any request. The client throws when the response does not echo the
`decision_id` it sent, because the run may have started without the link. A fourth argument, `{ reportedOrigin }`, sends the caller's
`reported_origin`; set it from the calling program, never from model or user input. See
[Calibration Sessions](../agent/calibration-sessions.md).

## Packaging and release

The package is ESM only, ships `dist/index.js` and `dist/index.d.ts`, and requires Node.js 20 or
later. `tsup` builds it with `@oqtopus-team/qdash-client` marked external. In the workspace the
dependency is `workspace:*`; the release pipeline packs the SDK at the client version of the
same run and pins the client to exactly that version, then publishes it after the client and
before pi-qdash. [Pi Packages](../agent/packages.md#distribution) describes the pipeline.

## Tests

| Test | Covers |
| --- | --- |
| `sdks/typescript/tests/sdk.test.ts` | Request bodies and `X-Project-Id` through a recording `fetch`, dispatch without a project, no wait on dispatch, whole-run status, pending 404 and timeout, 422 propagation, name checks before any request, keys against `docs/oas/openapi.json`, error identity with the built client |
| `sdks/typescript/tests/dashboards.test.ts` | Text-only `Script.fromFile`, panel IDs, layouts, hops and config, revision binding and `MetricScriptError`, request bodies, `expected_revision` and `expected_version`, 409 propagation |
| `sdks/typescript/tests/results.test.ts` | `compareLatest` with fixtures checked against the `TaskResultListItem` and `TaskResultResponse` schemas of `docs/oas/openapi.json`: list query parameters, detail reads, newest-first pairing, changed and unchanged values, key order and array order, `unavailable` and `insufficient`, identity mismatches, option checks before any request |
| `clients/typescript/tests/client.test.ts` | `waitForExecution` with and without `notFoundAsPending`, `withProject`, `listExecutions` and the task-history methods against the route parameters of `docs/oas/openapi.json` |
| `packages/pi-qdash/tests/qdash-sdk-package.test.mjs` | pi-qdash, the SDK and the built client resolve to one client copy; the client has no SDK subpath |
| `.github/scripts/sdk-package-release.test.mjs` | Stable and beta manifests, the client pin, publish tags and the job order in the release pipeline |
| `.github/scripts/sdk-package-smoke.mjs` | Run in CI against an npm install of the SDK and client tarballs: dependencies, one client copy, no bundled client, error identity, and a `nodenext` typecheck of the declarations |

## Implementation Files

- `sdks/typescript/src/session.ts`: `QDash`.
- `sdks/typescript/src/pipelines.ts`: `Pipelines`, `PipelineRun`, `Chip`, `CalibrationRun`.
- `sdks/typescript/src/workflows.ts`: `Workflows`, `Workflow`, `WorkflowRun`.
- `sdks/typescript/src/runs.ts`: `RunResult`, `runStatus`, the wait options.
- `sdks/typescript/src/results.ts`: `TaskResults`, `compareLatest`.
- `sdks/typescript/src/definitions.ts`: target, step and sweep helpers, `calibrationSpec`.
- `sdks/typescript/src/dashboards.ts`: `Script`, `Dashboard`, `ScriptMetric`, `Scripts`, `SavedScript`, `Dashboards`, `SavedDashboard`.
- `clients/typescript/src/client.ts`: `withProject` and `waitForExecution`.
- `.github/scripts/sdk-package-release.mjs`: release version, client pin and publish tag.
