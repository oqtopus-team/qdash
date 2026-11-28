# @oqtopus-team/qdash-sdk

`@oqtopus-team/qdash-sdk` validates and starts QDash calibrations on a chip, lists and runs
the workflows registered in a project, and saves metric scripts and dashboards. Its Fern-generated
API client is included; it does not depend on `@oqtopus-team/qdash-client`. Existing client
applications can continue using that package independently.

```bash
npm install @oqtopus-team/qdash-sdk
```

The package is ESM only and requires Node.js 20 or later. For a shared Python/TypeScript
profile, run `npx qdash config init --project-id your-project-id`, fill in `api_token`
in the generated file, and use `await QDash.fromProfile("local")` below. Use `--base-url` for a
remote deployment. The command creates a new TOML file with `[local]` and never overwrites
an existing file. For `QDash.fromEnv()`, set `QDASH_BASE_URL`, `QDASH_API_TOKEN`, and
`QDASH_PROJECT_ID` instead.

```ts
import { QDash, customOneQubit, qubitTargets } from "@oqtopus-team/qdash-sdk";

const qdash = QDash.fromEnv(); // or await QDash.fromProfile("local")
const chip = qdash.chip("64Qv3");
const steps = [customOneQubit({ step_name: "t1", tasks: [{ name: "CheckT1" }] })];

const check = await chip.validateCalibration(qubitTargets(["0", "1"]), steps); // nothing runs
if (!check.valid) throw new Error("Invalid calibration spec");
const run = await chip.calibrate(qubitTargets(["0", "1"]), steps); // measures
const result = await run.wait({ timeoutSeconds: 3600 });
console.log(run.executionId, result.status);
```

Check `check.valid` before calling `calibrate()`. The example measures real targets; choose them
for your deployment. `wait()` returns the whole run's status. A timeout leaves the run active; it stops further polling but does not cancel a read already in flight.
`QDashResultUnknownError` means a launch may have started, but its response is unreadable or
does not confirm the requested recording. Inspect its `executionId` when present before launching again.

See the [TypeScript reference](https://oqtopus-team.github.io/qdash/reference/clients/typescript)
for shared Python/TypeScript TOML profiles, workflows, metrics, and dashboards.
INI profiles remain readable with a deprecation warning. Reuse the session across operations;
there is no connection to close.

## Build Calibration Definitions

Import pure targets, task calls, all built-in steps, and sweeps from
`@oqtopus-team/qdash-sdk/calibration`, or from the package root. The subpath has no HTTP,
authentication, or Node.js runtime imports. Fields use Python's snake_case names; omitted
fields stay omitted, and valid explicit defaults and `null` are preserved. Builders reject
invalid local inputs; server validation still checks the chip, task catalog, and dependencies.
See the [definition reference](https://oqtopus-team.github.io/qdash/reference/clients/typescript#define-a-calibration)
for Python mappings and serialization rules.

## Summarize Task Results

Reuse a configured `qdash` session to aggregate multiple pages:

```ts
const summary = await qdash.taskResults.summarize({ chipId: "64Qv3", maxRows: 1000 });
if (!summary.complete) console.warn(summary.diagnostics);
console.log(summary.aggregates.byStatus);
```

Aggregates count only the distinct rows read. Check `complete` before treating them as full
counts; even a complete offset read is not a snapshot. See the
[summary contract](https://oqtopus-team.github.io/qdash/reference/clients/typescript#summarize-task-results)
for filters, limits, and recovery.

## Read a Result with Context

Reuse a configured `qdash` session and a task ID from `qdash.api.taskResult.listTaskResults()`:

```ts
const page = await qdash.api.taskResult.listTaskResults({ chip_id: "64Qv3", qid: "0", limit: 1 });
if (!page.items[0]) throw new Error("No saved results for this target");
const evidence = await qdash.taskResults.evidence(page.items[0].task_id);
console.log(evidence.result.output_parameters);
if (evidence.target.status === "ok") console.log(evidence.target.value.outputs);
```

This reads the result, its execution, and its target's current stored values. Secondary reads
report missing or failed context without discarding the result. Cooldown is `not_associated`
unless you pass `{ cooldownId }`; a supplied cooldown is checked, not treated as proven provenance.
See the [result context contract](https://oqtopus-team.github.io/qdash/reference/clients/typescript#read-a-result-with-context).

Use `qdash.read` and `qdash.send` for generated reads and writes with SDK error handling,
or `qdash.fetch` for a response body such as a figure download. See the
[API reference](https://oqtopus-team.github.io/qdash/reference/clients/typescript#generated-api).

## Develop the Package

Install from the repository root. Generation checks require Node.js (`npx`) and Docker:

```bash
bun install --frozen-lockfile
task test-sdk-ts
```
