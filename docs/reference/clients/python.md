# Python Client

Use `qdash-client` to read the API and `qdash-sdk` to define and run calibrations. Both support
Python 3.11–3.12; the SDK installs the matching client version.

## Install the Package

```bash
pip install qdash-client
# For calibration and dashboard authoring:
pip install qdash-sdk
```

Stable versions follow QDash releases. Use `pip install --pre qdash-sdk` for a prerelease.

## Connect to a Deployment

<a id="configuration"></a>

1. Copy your token from **Settings → API Token**. The displayed curl example includes the project ID.
2. Save a profile, keeping the `/api` suffix in the base URL:

   ```python
   from getpass import getpass
   from qdash.client import QDashConfig

   QDashConfig(
       base_url="http://localhost:5714/api",
       api_token=getpass("QDash API token: "),
       project_id="your-project-id",
   ).save("local")
   ```

### Profiles

Profiles live in `$XDG_CONFIG_HOME/qdash/config.ini`, or `~/.config/qdash/config.ini`.
`save()` writes owner-only permissions. Load one with `QDashClient.from_profile("local")`.

### Environment Variables

Use `QDashClient.from_env()` to read these settings instead:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `QDASH_BASE_URL` | Required | QDash API base URL |
| `QDASH_API_TOKEN` | None | Bearer token |
| `QDASH_PROJECT_ID` | None | Active project header |
| `QDASH_CF_ACCESS_CLIENT_ID` | None | Cloudflare Access client ID |
| `QDASH_CF_ACCESS_CLIENT_SECRET` | None | Cloudflare Access client secret |
| `QDASH_TIMEOUT_SECONDS` | `30` | Request timeout |
| `QDASH_MAX_WORKERS` | `4` | Concurrent worker limit |
| `QDASH_RETRY_MAX_ATTEMPTS` | `3` | Maximum attempts for a request the client may send again |
| `QDASH_RETRY_BACKOFF_SECONDS` | `0.2` | Initial retry delay |
| `QDASH_RETRY_MAX_BACKOFF_SECONDS` | `5.0` | Maximum retry delay |
| `QDASH_VERIFY_TLS` | `true` | TLS certificate verification |
| `QDASH_PROXY` | None | HTTP proxy URL |
| `QDASH_USER_AGENT` | Package version | Custom user-agent value |

Legacy password authentication uses `QDASH_USERNAME` and the variable named by
`QDASH_PASSWORD_ENV` (default `QDASH_PASSWORD`).

## Call the High-Level API

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
qdash.close()
```

`validate_calibration()` dispatches nothing. `calibrate()` dispatches and returns a run;
`run.wait()` returns its whole-calibration status, including failure or cancellation.
A timeout leaves the run active. Close the SDK when done, or use `with QDash.from_profile("local") as qdash:`.

### Run a Whole Pipeline Spec

For a stored spec, use `qdash.pipelines.validate(spec, chip_id=...)` and
`qdash.pipelines.execute(spec, chip_id=...)`. The returned run's `wait()` returns the raw execution
detail. See [Pipeline specs](../../developer-guide/workflow/calibration-pipeline.md).

## Run a Registered Workflow

First [save a workflow](../../user-guide/creating-workflows.md); replace `coherence_check` below
with its **Flow Name** and choose targets supported by that workflow.

```python
from qdash.sdk import QDash

with QDash.from_profile("local") as qdash:
    workflow = qdash.workflows.get("coherence_check")
    result = workflow.run(parameters={"qids": ["0", "1"]}).wait()
    print(result.status)
```

`qdash.workflows.list()` lists saved workflows. Parameters override saved defaults for this run
only; nothing is uploaded. A project is required for execution.

## Save Metric Scripts and Dashboards

```python
from qdash.sdk import Dashboard, QDash

with QDash.from_profile("local") as qdash:
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

Use `qdash.client.rest` only when a high-level method is unavailable. High-level methods share
authentication, project headers, retries, and validation.
