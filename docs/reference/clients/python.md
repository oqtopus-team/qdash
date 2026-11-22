# Python Client

`qdash-client` provides typed, high-level access to QDash for scripts, notebooks, exporters, and
agent integrations. It supports Python 3.11 and 3.12.

## Install the Package

```bash
pip install qdash-client
```

`qdash-client` provides `qdash.client`, one method per API route. To also define and run
[calibrations](#run-a-calibration) with `qdash.sdk`, install
`qdash-sdk`, which installs the `qdash-client` of the same version:

```bash
pip install qdash-sdk
```

In a uv project, run `uv add qdash-sdk` or `uv add qdash-client`.

Each QDash release tag `vX.Y.Z` publishes `qdash-client` and `qdash-sdk` `X.Y.Z` to PyPI, the
same version as the [TypeScript client](./typescript.md). Each change on `develop` that publishes a
[TypeScript client beta](./typescript.md#installation) also publishes a PEP 440 pre-release,
`<next QDash patch>b<build>`, where `<build>` counts the first-parent commits on `develop` (for
example `1.10.3b1278`); the TypeScript client spells the same build `1.10.3-beta.1278`. The
Python release reuses the version computed for the npm release and publishes after it, so a
version can reach npm before PyPI.
pip installs pre-releases only on request:

```bash
pip install --pre qdash-sdk
```

Every `qdash-sdk` release requires exactly the `qdash-client` release of its own version, stable
or pre-release, so the installed pair always matches. With uv, run
`uv add --prerelease allow qdash-sdk`.

## Connect to a Deployment

<a id="configuration"></a>

Save an API token in a named profile so scripts can connect without embedding credentials:

1. In QDash, open **Settings → API Token** and copy **Your Access Token**. The
   **Example Usage (curl)** command beside it shows the active project's ID in its
   `X-Project-Id` header.
2. Save a profile with the API base URL, the token, and the project ID:

   ```python
   from getpass import getpass

   from qdash.client import QDashConfig

   QDashConfig(
       base_url="http://localhost:5714/api",
       api_token=getpass("QDash API token: "),
       project_id="your-project-id",
   ).save("local")
   ```

3. Check the connection:

   ```python
   from qdash.client import QDashClient

   client = QDashClient.from_profile("local")
   try:
       print(client.list_chips().total)
   finally:
       client.close()
   ```

A Docker Compose deployment serves the API under `/api` on `UI_PORT`, so the base URL is
`http://<host>:<UI_PORT>/api`, or the public URL followed by `/api` behind
[remote access](../../user-guide/setup.md#enable-remote-access).

### Profiles

`QDashConfig.save()` creates or updates a profile in `$XDG_CONFIG_HOME/qdash/config.ini`, or
`~/.config/qdash/config.ini` when `XDG_CONFIG_HOME` is unset, with owner-only permissions
(`0600`). A profile section uses the setting names below in lowercase without the `QDASH_` prefix:

```ini
[prod]
base_url = https://your-qdash-instance/api
api_token = your-api-token
project_id = your-project-id
timeout_seconds = 30
retry_max_attempts = 3
```

`QDashClient.from_profile("prod")` loads a profile; `QDashClient()` without a configuration loads
the `default` profile.

### Environment Variables

In a secret-managed environment, supply the same settings as environment variables and use
`QDashClient.from_env()`. `QDASH_BASE_URL` is the only required variable; include the API path
prefix, such as `/api`.

```bash
export QDASH_BASE_URL="https://your-qdash-instance/api"
export QDASH_API_TOKEN="your-api-token"
export QDASH_PROJECT_ID="your-project-id"
```

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

Legacy deployments can use `QDASH_USERNAME` and the password variable named by
`QDASH_PASSWORD_ENV`, which defaults to `QDASH_PASSWORD`.

## Call the High-Level API

Close the client after use so its HTTP session is released:

```python
from qdash.client import QDashClient

client = QDashClient.from_profile("local")
try:
    chip = client.get_default_chip()
    metrics = client.get_chip_metrics(chip.chip_id)
    print(metrics.qubit_metrics)
finally:
    client.close()
```

The high-level client groups operations by domain:

| Domain | Primary methods |
| --- | --- |
| Chips and metrics | `list_chips`, `get_default_chip`, `get_chip_metrics`, `get_metrics_config`, qubit and coupling getters |
| Task results | `list_task_results`, latest-result and history getters, `get_task_result`, notes, exclusion, and re-execution |
| Projects and files | Project getters, file tree and content, validation, and configuration Git operations |
| Issues and knowledge | Issue lifecycle, approved knowledge, and task knowledge operations |
| Flows and executions | Flow templates, save, execute, schedule, wait, and cancel operations |
| Calibration pipelines | `get_calibration_pipeline_catalog`, `validate_calibration_pipeline`, `execute_calibration_pipeline` |
| Provenance | Entity, lineage, impact, history, statistics, and recent-change operations |
| Agent calibration | Sessions, actions, candidate gates, commits, apply operations, polling helpers, and interventions (`create_agent_intervention`, `get_agent_intervention`, `list_agent_interventions`, `claim_agent_resume`, `record_agent_resume_outcome`) |

Methods return Pydantic models exported from `qdash.client`. Configuration failures raise
`QDashConfigError`; API and transport failures raise subclasses of `QDashApiError`:

| Exception | Condition |
| --- | --- |
| `QDashConfigError` | Missing or invalid local configuration |
| `QDashAuthError` | Missing or rejected authentication |
| `QDashNotFoundError` | HTTP 404 |
| `QDashValidationError` | Invalid request arguments or an unexpected response shape |
| `QDashTransportError` | Network failure, timeout, or another unexpected HTTP status |

`QDASH_RETRY_MAX_ATTEMPTS` bounds three kinds of resend:

| Failure | Resent |
| --- | --- |
| Network failure or timeout on a `GET` | Yes |
| Connection never made (`POST`, `PUT`, `PATCH`, or `DELETE`) | Yes, because the server never received the request |
| Timeout or dropped connection after a write was sent | No; it raises `QDashTransportError`, because the server may already have acted on it |
| HTTP 401 with username and password authentication | Yes, after a fresh login, because the server rejected the request without acting on it |

The client does not resend on any other HTTP status. Before repeating a failed write, check its
effect, for example with `list_executions` after `execute_flow`.

`wait_for_execution` polls until the execution reaches `completed`, `failed`, `cancelled`,
`canceled`, or `crashed`. For one step of a
[calibration pipeline](../../developer-guide/workflow/calibration-pipeline.md#following-a-run) it
waits for the whole run and reads `pipeline.status`; pass `whole_pipeline=False` to wait for that
step's execution only. A failed or cancelled execution is returned, not raised, and the call raises
`TimeoutError` after `timeout_seconds`.

`with_project(project_id)` returns a client that sends another `X-Project-Id` and shares this
client's connection and credentials. The original client is unchanged; close it, not the copy,
to release the connection.

Only `list_chips_async`, `get_task_results_timeseries_async`, and `get_metrics_config_async` have
async variants. They use the same `QDashClient` configuration and close their temporary async HTTP
clients after each request. Call `close()` to release the persistent synchronous transport.

## Run a Calibration

`qdash.sdk`, from the `qdash-sdk` package, starts a calibration on a chip from Python objects:
targets, and steps that run in order, as `CalibService.run(targets, steps)` takes them in a
[workflow](../../developer-guide/workflow/services.md). This calibration runs `Configure`,
`CheckT1` and `CheckT2Echo` on qubits 0 and 1 with the sweeps of the `coherence_check`
template:

```python
import math

from qdash.sdk import QDash
from qdash.sdk.calibration import CustomOneQubit, QubitTargets, TaskCall, sweep

qdash = QDash.from_env()
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

| Call | Result |
| --- | --- |
| `QDash.from_env()`, `QDash.from_profile(...)` | A session with its own `QDashClient`; nothing is sent |
| `qdash.chip(chip_id)` | A `Chip` bound to the session's client, project and `chip_id`; nothing is sent |
| `QubitTargets(qids)`, `MuxTargets(mux_ids, exclude_qids=...)` | Explicit qubits, or every qubit of the MUXes except the excluded ones |
| `CustomOneQubit(step_name=..., tasks=[...])`, `TaskCall(name=..., run=...)` | A step that runs its task calls in order on each target qubit |
| `chip.validate_calibration(targets, steps, ...)` | `ValidatePipelineResponse`; problems are data, nothing is dispatched |
| `chip.calibrate(targets, steps, ...)` | `CalibrationRun`; dispatches one execution, raises `QDashValidationError` (422) for a calibration with problems and `QDashConfigError` without a project |
| `run.wait(timeout_seconds=3600, poll_interval_seconds=5)` | `RunResult` once the whole calibration ends; `TimeoutError` otherwise, and the run keeps going |
| `run.get()` | `RunResult` for the current state, without waiting |

`validate_calibration` and `calibrate` take the same arguments: `targets`, `steps`, and the
optional `name` (the execution's display name), `default_run_parameters` (the run parameters
every task call starts from), `tags` and `backend_name`. The server's defaults apply to each one
left out. `calibrate` does not call `validate_calibration`; the server validates again before
dispatch.

`result.status` is the whole calibration's status, `completed`, `failed` or `cancelled` once it
ends, not the status of its first step's execution. A failed or cancelled calibration is returned,
not raised. `result.detail` is the execution detail as `get_execution` returns it, with every
step's progress in `result.detail.pipeline`, and `result.execution_id` names the first step's
execution.

Building the definitions checks only their structure, such as required fields, ID patterns and
literal values. The server decides whether a calibration can run, including task names, repeated
call IDs and the calibration data each task needs. A valid check is not a hardware safety check
beyond those rules. Other step types are passed as their generated models from
`qdash.client.services.models` or as dictionaries in the spec's JSON form.

A session keeps one connection for all its calls, so a script or notebook creates it once and
calls `qdash.close()` when done; `with QDash.from_env() as qdash:` calls `close()` on exit.
`QDash(client)` uses an existing client and `close()` leaves it open. `project_id=...` on any of
them scopes the session to another project without changing the client's configuration.

### Run a Whole Pipeline Spec

`qdash.pipelines` works with a whole [calibration pipeline spec](../../developer-guide/workflow/calibration-pipeline.md),
for a spec kept as a file or built with `Pipeline` from `qdash.sdk.pipeline`, which also exports
the definitions above:

```python
from qdash.sdk.pipeline import Pipeline

pipeline = Pipeline(
    name="coherence-t1-t2echo",
    targets=targets,
    steps=steps,
    default_run_parameters=run_parameters,
)
spec = pipeline.to_spec()  # the spec version 2 JSON object; nothing is sent
check = qdash.pipelines.validate(spec, chip_id="64Qv3")
pipeline_run = qdash.pipelines.execute(spec, chip_id="64Qv3")
detail = pipeline_run.wait(timeout_seconds=3600)
print(detail.pipeline.status if detail.pipeline else detail.status)
```

| Call | Result |
| --- | --- |
| `qdash.pipelines.catalog(backend_name=None)` | Step types, task names by type, and the spec schema |
| `qdash.pipelines.validate(pipeline, chip_id=...)` | `ValidatePipelineResponse`; a `Pipeline` or a spec mapping, sent unchanged |
| `qdash.pipelines.execute(pipeline, chip_id=...)` | `PipelineRun`; the same errors as `chip.calibrate` |
| `pipeline_run.wait(...)` | The raw `ExecutionResponseDetail` once the whole pipeline ends |

## Run a Registered Workflow

`qdash.workflows` lists, inspects and runs the workflows registered in the session's project: flows
saved from the UI or with `save_flow`, each with a deployment and the chip it was saved for. Unlike
`chip.calibrate`, which sends the steps it should run, a registered workflow runs code already
stored in QDash:

```python
for summary in qdash.workflows.list():
    print(summary.name, summary.chip_id, summary.description)

workflow = qdash.workflows.get("coherence_check")
print(workflow.chip_id, workflow.default_parameters)

run = workflow.run(parameters={"qids": ["0", "1"]})  # measures
result = run.wait(timeout_seconds=3600)
print(result.status)
```

| Call | Result |
| --- | --- |
| `qdash.workflows.list()` | A list of `FlowSummary` with `name`, `chip_id`, `description`, `tags` and `folder`; nothing is run |
| `qdash.workflows.get(name)` | A `Workflow` with `name`, `chip_id`, `description`, `default_parameters` and the raw `GetFlowResponse` as `detail`; `QDashNotFoundError` for a name the project does not have |
| `workflow.run(parameters=...)`, `qdash.workflows.run(name, parameters=...)` | `WorkflowRun` with `execution_id` and the raw `ExecuteFlowResponse` as `response`; `QDashConfigError` without a project |
| `run.wait(...)`, `run.get()` | `RunResult`, read the same way as a calibration's |

`parameters` override the saved `default_parameters` for this run only; without them the run uses
the saved defaults. The workflow runs on its saved `chip_id` unless the saved defaults or the
parameters carry a `chip_id`. `default_parameters` lists the saved values, not every parameter the flow function
accepts; the source is in `workflow.detail.code`. A name other than letters, digits and
underscores raises `ValueError` before any request. Nothing is uploaded, registered or run
locally.

How the SDK is built: [Python SDK](../../developer-guide/architecture/python-sdk.md).

## Save Metric Scripts and Dashboards

`qdash.scripts` and `qdash.dashboards` save [metric scripts](../../user-guide/metric-scripts.md)
and [dashboards](../../user-guide/dashboards.md) defined in Python. This example
saves the median ZX90 fidelity script from a file and shares a dashboard that shows it per
directed coupling over the last 14 days:

```python
from qdash.sdk import Dashboard, QDash, Script

qdash = QDash.from_env(project_id="my-project")
script = qdash.scripts.create(Script.from_file("zx90_median.py", visibility="project"))
zx90 = script.metric("zx90_median")

board = Dashboard("ZX90 health", visibility="project", chip_id="64Qv3")
board.add_metric(zx90, period=14, params={"min_samples": 3})
saved = qdash.dashboards.create(board)
print(saved.dashboard_id, saved.version)
```

A grid of frequency collision checks starts from the starter template and places panels
explicitly:

```python
collision = qdash.scripts.create(qdash.scripts.template("collision", visibility="project"))
grid = Dashboard("Collision checks", visibility="project")
for index, kind in enumerate(["Type0A", "Type0B", "Type1A", "Type3A"]):
    grid.add_metric(collision.metric(kind), period=30, layout=(6 * (index % 2), 4 * (index // 2), 6, 4))
qdash.dashboards.create(grid)
```

| Call | Result |
| --- | --- |
| `Script(name, source, ...)`, `Script.from_file(path, ...)` | A local script; the file is read as text, never run |
| `qdash.scripts.template(template_id, ...)` | A local `Script` with a starter template's source |
| `qdash.scripts.validate(script)` | The catalog or diagnostics; nothing is saved |
| `qdash.scripts.create(script)`, `qdash.scripts.update(target, script)` | `SavedScript` bound to the revision the save produced; unchanged source adds no revision |
| `qdash.scripts.get(script_id, revision=None)` | `SavedScript` bound to the active revision or the one named |
| `saved_script.metric(metric_id)` | `ScriptMetric` for a panel; `MetricScriptError` when the bound revision is invalid or lacks the metric |
| `Dashboard(name, ...)`, `board.add_metric(metric, ...)`, `board.add_markdown(content, ...)` | A local dashboard; panels go below the existing ones with readable IDs |
| `qdash.dashboards.create(board)` | `SavedDashboard` with `dashboard_id`, `version` and the raw response |
| `qdash.dashboards.get(dashboard_id)`, `saved.edit()` | The stored dashboard, and a local copy to change |
| `qdash.dashboards.update(target, board)` | Replaces settings and panels; 409 when the dashboard changed since the version it is based on |

A panel pins the script revision of its `ScriptMetric`, so later script saves do not change it.
`add_metric` defaults `hops` to the metric's declared distances and `period` to 14 days. A
script that creates several objects keeps whatever was saved before a failure: the SDK neither
retries nor rolls back. A 409 is raised as `QDashApiError` with `status_code` 409; read the
dashboard again before saving.

## Agent Calibration

`AgentCalibrationRunner` runs one bounded step and `AgentPlanRunner` runs an approved graph of
steps. Both use `QDashClient` for session policy, execution, candidate validation, commit, and
backend-apply operations.

```python
from qdash.client import AgentCalibrationRunner, QDashClient

client = QDashClient.from_profile("local")
try:
    outcome = AgentCalibrationRunner(client).run_step(
        session_id="SESSION_ID",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="SOURCE_EXECUTION_ID",
        candidate_parameter="t1",
    )
    print(outcome.transition, outcome.reason)
finally:
    client.close()
```

The runner does not create the approved scope implicitly. Create and review the session first, then
handle `pass`, `retry`, `rollback`, and `human_escalation` as described in
[Agent Calibration](../../user-guide/agent-calibration.md). With `record_interventions=True`,
`run_plan` records a non-pass ending as an intervention and returns it in `outcome.intervention`
(or the failure in `outcome.intervention_error`). When QDash rejects only the checkpoint
(`checkpoint_rejected`), the stop is recorded without one, QDash's reason is in
`outcome.checkpoint_rejection`, and that intervention cannot resume the plan.
`resume_state_from_intervention` turns a claimed
intervention into the nodes, `AgentPlanResumeState`, and settings that `run_plan(resume=...)`
continues from.

## Use the Low-Level Client

`qdash.client.rest` exposes the generated transport for operations that do not yet have a
high-level method. Prefer `QDashClient` when a high-level method exists because it supplies shared
authentication, project headers, retries, response validation, and error mapping.
