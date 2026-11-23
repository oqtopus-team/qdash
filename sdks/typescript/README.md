# @oqtopus-team/qdash-sdk

`@oqtopus-team/qdash-sdk` validates and starts QDash calibrations on a chip, lists and runs
the workflows registered in a project, and saves metric scripts and dashboards. It is built on
[`@oqtopus-team/qdash-client`](https://www.npmjs.com/package/@oqtopus-team/qdash-client), which
stays the lower-level API for every other route. Installing the SDK installs the client of the
same release:

```bash
npm install @oqtopus-team/qdash-sdk
```

The package is ESM only and requires Node.js 20 or later.

```ts
import { QDash, customOneQubit, qubitTargets } from "@oqtopus-team/qdash-sdk";

const qdash = QDash.fromEnv(); // or new QDash(client, { projectId: "your-project-id" })
const chip = qdash.chip("64Qv3");
const steps = [customOneQubit({ step_name: "t1", tasks: [{ name: "CheckT1" }] })];

const check = await chip.validateCalibration(qubitTargets(["0", "1"]), steps); // nothing runs
if (!check.valid) throw new Error("Invalid calibration spec");
const run = await chip.calibrate(qubitTargets(["0", "1"]), steps); // measures
const result = await run.wait({ timeoutSeconds: 3600 });
console.log(run.executionId, result.status);
```

Check `check.valid` before calling `calibrate()`. The example measures real targets; choose them
for your deployment. `wait()` returns the whole run's status. A timeout leaves the run active.

See the [TypeScript reference](https://oqtopus-team.github.io/qdash/reference/clients/typescript)
for configuration, workflows, metrics, and dashboards.

## Develop the Package

Install from the repository root; the SDK builds against the client in the same checkout:

```bash
bun install --frozen-lockfile
task test-sdk-ts
```
