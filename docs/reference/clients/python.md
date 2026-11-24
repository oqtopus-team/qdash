# Python Client and SDK

Use `qdash-sdk` for API access, calibration, workflows, and dashboards. It includes its own
generated API client. Existing `qdash-client` applications remain supported independently;
both packages support Python 3.11–3.12 and can coexist.

## Install the Package

```bash
pip install qdash-sdk
# For existing applications using qdash.client:
pip install qdash-client
```

Stable versions follow QDash releases. Use `pip install --pre qdash-sdk` for a prerelease.

## Connect to a Deployment

<a id="configuration"></a>

1. Copy your token from **Settings → API Token**. The displayed curl example includes the project ID.
2. Create the profile file at `$XDG_CONFIG_HOME/qdash/config.ini`, or
   `~/.config/qdash/config.ini` when `XDG_CONFIG_HOME` is unset. Restrict the file to your user
   (`chmod 600 /path/to/config.ini`) before adding the token. Preserve any existing profiles.
   Add this section, replacing the URL, token, and project ID for your deployment:

   ```ini
   [local]
   base_url = http://localhost:5714/api
   api_token = your-api-token
   project_id = your-project-id
   ```

### Profiles

Load the profile with `QDash.from_profile("local")`. Existing client applications use
`QDashClient.from_profile("local")` with the same file. Applications with `qdash-client`
installed can also write profiles with that package's `QDashConfig.save()`.
For configuration without a file, pass `qdash.sdk.QDashConfig(...)` to `QDash(...)`.

### Environment Variables

Use `QDash.from_env()` or `QDashClient.from_env()` to read these settings instead:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `QDASH_BASE_URL` | Required | QDash API base URL |
| `QDASH_API_TOKEN` | None | Bearer token |
| `QDASH_PROJECT_ID` | None | Active project header |
| `QDASH_CF_ACCESS_CLIENT_ID` | None | Cloudflare Access client ID |
| `QDASH_CF_ACCESS_CLIENT_SECRET` | None | Cloudflare Access client secret |
| `QDASH_TIMEOUT_SECONDS` | `30` | Request timeout |
| `QDASH_MAX_WORKERS` | `4` | Existing client only: concurrent worker limit |
| `QDASH_RETRY_MAX_ATTEMPTS` | `3` | Maximum attempts for a request the client may send again |
| `QDASH_RETRY_BACKOFF_SECONDS` | `0.2` | Existing client only: initial retry delay |
| `QDASH_RETRY_MAX_BACKOFF_SECONDS` | `5.0` | Existing client only: maximum retry delay |
| `QDASH_VERIFY_TLS` | `true` | TLS certificate verification |
| `QDASH_PROXY` | None | HTTP proxy URL |
| `QDASH_USER_AGENT` | Package version | Custom user-agent value |

Legacy password authentication uses `QDASH_USERNAME` and the variable named by
`QDASH_PASSWORD_ENV` (default `QDASH_PASSWORD`).

## Access the API through the SDK

```python
from qdash.sdk import QDash

qdash = QDash.from_profile("local")
print(qdash.api.chip.list_chips().total)
```

Create one session and reuse `qdash` across notebook cells or script operations. Each example
below includes initialization so it can run on its own; skip that line when reusing your session.
Call `qdash.close()` when you finish using the connection. For a short script that needs
automatic cleanup, `with QDash.from_profile("local") as qdash:` is also supported.
Closing the connection does not cancel work already dispatched to the server.

`qdash.api` exposes the generated resources, grouped by API tags. Response types are available
from `qdash.sdk.types`. These calls use the session's authentication and project header,
perform no automatic retries by default, and raise generated `ApiError` subclasses or httpx
exceptions. SDK helpers such as `qdash.workflows.run()` translate failures to SDK errors;
HTTP 409 becomes `QDashConflictError`. Helper reads use `QDASH_RETRY_MAX_ATTEMPTS`; helper
writes are sent once. Do not enable retries on execution writes without reconciling their effects.

`qdash.with_project(project_id)` shares the connection; close the original session after both
are done. Token authentication is preferred. Password authentication caches a login token;
create a new session if that token expires.

`QDash` sessions and helpers are synchronous. The exported `AsyncQDashApi` is a separate
generated client: configure its base URL, authentication, and project explicitly; it does not
inherit a `QDash` session's configuration.

## Call the Existing Client's High-Level API

```python
from qdash.client import QDashClient

client = QDashClient.from_profile("local")
try:
    print(client.list_chips().total)
finally:
    client.close()
```

A count of `0` is a successful connection to a project with no chips. Before calibration examples,
[create a chip and run its first calibration](../../user-guide/first-calibration.md).

Methods return typed models. `with_project(project_id)` shares the connection but changes the
project header; close the original client. See [OpenAPI](../openapi.md) for the full API.

| Failure | Exception |
| --- | --- |
| Invalid configuration | `QDashConfigError` |
| Authentication | `QDashAuthError` |
| Missing record | `QDashNotFoundError` |
| Invalid arguments or response | `QDashValidationError` |
| Network or other HTTP failure | `QDashTransportError` |

GET transport failures and writes that never connected may be retried. A write that times out
after sending is not retried: check its effect before repeating it. Password authentication may
retry after a rejected login; other HTTP statuses are not retried.

`wait_for_execution()` returns failed or cancelled runs as results. A timeout raises
`TimeoutError` and does not cancel the run. For pipeline steps it waits for the whole pipeline;
use `whole_pipeline=False` for only that step.

## Run a Calibration

The remaining examples use the `local` profile saved above. Set its project ID and replace
`64Qv3` with your chip ID. This example measures qubits 0 and 1; use targets and task
settings appropriate for your hardware. Validation checks the spec, not physical safety.

```python
import math
from qdash.sdk import QDash
from qdash.sdk.calibration import CustomOneQubit, QubitTargets, TaskCall, sweep

qdash = QDash.from_profile("local")
chip = qdash.chip("64Qv3")

time_range = sweep.logspace(math.log10(300), math.log10(500_000), 51)
targets = QubitTargets(["0", "1"])
steps = [
    CustomOneQubit(
        step_name="coherence",
        tasks=[
            TaskCall(name="Configure"),
            TaskCall(name="CheckT1", run={"time_range": time_range}),
            TaskCall(name="CheckT2Echo", run={"time_range": time_range}),
        ],
    ),
]
run_parameters = {"readout_duration": 1024, "interval": 262_144}

check = chip.validate_calibration(targets, steps, default_run_parameters=run_parameters)
if not check.valid:
    raise SystemExit([f"{p.path}: {p.message}" for p in check.problems or []])

run = chip.calibrate(targets, steps, default_run_parameters=run_parameters)  # measures
result = run.wait(timeout_seconds=3600)
print(result.status)
```

`validate_calibration()` dispatches nothing. `calibrate()` dispatches and returns a run;
`run.wait()` returns its whole-calibration status, including failure or cancellation.
A timeout leaves the run active. Keep the session to inspect or follow the run later.

### Run a Whole Pipeline Spec

For a stored spec, use `qdash.pipelines.validate(spec, chip_id=...)` and
`qdash.pipelines.execute(spec, chip_id=...)`. The returned run's `wait()` returns the raw execution
detail. See [Pipeline specs](../../developer-guide/workflow/calibration-pipeline.md).

## Run a Registered Workflow

First [save a workflow](../../user-guide/creating-workflows.md); replace `coherence_check` below
with its **Flow Name** and choose targets supported by that workflow.

```python
from qdash.sdk import QDash

qdash = QDash.from_profile("local")
workflow = qdash.workflows.get("coherence_check")
result = workflow.run(parameters={"qids": ["0", "1"]}).wait()
print(result.status)
```

`qdash.workflows.list()` lists saved workflows. Parameters override saved defaults for this run
only; nothing is uploaded. A project is required for execution.

## Follow an Existing Run

```python
from qdash.sdk import QDash

qdash = QDash.from_profile("local")
result = qdash.run("your-execution-id").wait(timeout_seconds=600)
print(result.status)
```

Replace the ID with one returned by an earlier launch. Creating the handle does not dispatch
work. Waiting follows the whole pipeline, returns failed or cancelled outcomes, and raises
`TimeoutError` without cancelling the run.

## Save Metric Scripts and Dashboards

```python
from qdash.sdk import Dashboard, QDash

qdash = QDash.from_profile("local")
script = qdash.scripts.create(qdash.scripts.template("zx90_median", visibility="project"))
board = Dashboard("ZX90 health", visibility="project", chip_id="64Qv3")
board.add_metric(script.metric("zx90_median"), period=14, params={"min_samples": 3})
saved = qdash.dashboards.create(board)
print(saved.dashboard_id)
```

This uses the built-in **Median ZX90 fidelity** template; no local source file is needed.
For your own calculation, see [metric scripts](../../user-guide/metric-scripts.md).
Panels pin the saved script revision. To edit a dashboard, get it, call `edit()`, then
`qdash.dashboards.update(saved, edited)`. HTTP 409 means it changed; read it again before saving.
Earlier successful saves remain if a later operation fails.

## Agent Calibration

`AgentCalibrationRunner` runs a bounded step; `AgentPlanRunner` runs an approved graph.
Neither creates approval implicitly. Follow [Agent Calibration](../../user-guide/agent-calibration.md)
for session scope, candidate review, and expert intervention.

## Use the Low-Level Client

For existing `qdash-client` applications, use `qdash.client.rest` only when a high-level method is unavailable. High-level methods share
authentication, project headers, retries, and validation.
