# @oqtopus-team/qdash-sdk

`@oqtopus-team/qdash-sdk` validates and starts QDash calibrations on a chip and lists and runs
the workflows registered in a project. It is built on
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
const run = await chip.calibrate(qubitTargets(["0", "1"]), steps); // measures
const result = await run.wait({ timeoutSeconds: 3600 });
console.log(run.executionId, result.status);
```

`result.status` is the whole pipeline run's status. A timeout throws `QDashTimeoutError` and
leaves the run going. `qdash.workflows.list()`, `get(name)` and `run(name, { parameters })` reach
the project's registered workflows. The SDK sends requests through the given `QDashClient`, and
its error classes are the client's own, so `instanceof` works with either import. A session
without a project uses the client's configuration as it is: when no project is configured
there, QDash applies the user's default project.

The [TypeScript client reference](https://oqtopus-team.github.io/qdash/reference/clients/typescript#run-a-calibration)
covers configuration and every call.

## Develop the Package

Install from the repository root; the SDK builds against the client in the same checkout:

```bash
bun install --frozen-lockfile
task test-sdk-ts
```
