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
2. Generate the initial configuration with your deployment's URL and project ID:

   ```bash
   qdash config init --base-url http://localhost:5714/api --project-id your-project-id
   ```

   This creates `$XDG_CONFIG_HOME/qdash/config.toml`, or `~/.config/qdash/config.toml`
   when `XDG_CONFIG_HOME` is unset, with `default_profile = "local"` and a `[local]`
   table. It creates parent directories and restricts the new file to your user on POSIX.
   If the file already exists, edit it or use `--path /path/to/config.toml`; the command
   never overwrites it. If `qdash` is not on your PATH, use `python -m qdash.sdk config init`
   with the same options.

3. Open the printed file path and paste your token into `api_token = ""`. Keep the file
   readable only by your user. Verify the connection with the
   [API read example](#access-the-api-through-the-sdk).

### Initialize a Configuration

`qdash config init` creates one profile without contacting the server or requiring a token.
The file enables `base_url`, an empty `api_token`, `timeout_sec = 30`, `verify_tls = true`,
and `read_attempts = 3`. Every other supported profile field appears as a commented example
with its purpose. `--project-id` enables the project setting when supplied.

To use an environment variable instead of storing a token in the file, pass
`--api-token-env QDASH_LOCAL_TOKEN` when creating it, then set that variable before connecting.
For an existing file, remove `api_token` and uncomment `api_token_env` instead.

| Option | Default | Purpose |
| --- | --- | --- |
| `--profile NAME` | `local` | Profile to create and select as `default_profile` |
| `--base-url URL` | `http://localhost:5714/api` | QDash API base URL |
| `--project-id ID` | Omitted | Project for SDK operations |
| `--api-token-env NAME` | Omitted; empty `api_token` enabled | Use an environment variable instead of a token in the file |
| `--path FILE` | Default configuration path | New file ending in `.toml` |

### Profiles

```toml
default_profile = "local"

[local]
base_url = "http://localhost:5714/api"
api_token = "<your-api-token>"
project_id = "your-project-id"
```

Add another top-level table, such as `[production]`, for another deployment.
Profile names must be nonempty; `default_profile` and `profiles` are reserved.
Quote names containing dots, such as `["lab.device"]`, to keep them as one profile.

`QDash()` and `QDash.from_profile()` select `default_profile`, or `"default"` when that
key is absent. `QDash.from_profile("local")` selects the named profile. A missing or invalid
configuration raises `QDashConfigError`; it does not fall back to environment settings.
Reuse the returned client across operations. `QDash.from_profile("local", path="/path/to/config.toml")` reads only that file.
For configuration without a file, pass `qdash.sdk.QDashConfig(...)` to `QDash(...)`.

Each top-level `[<name>]` table accepts `QDashConfig` fields and `api_token_env`. The latter
names an environment variable; a missing or empty variable is an error. Set either
`api_token_env` or `api_token`, not both. If you store a token directly, restrict the file to
your user (`chmod 600 /path/to/config.toml`). Other environment variables do not override a
profile; use `from_env()` to configure the session from environment variables instead.

### Migrate Nested TOML Profiles

The SDK no longer accepts `[profiles.<name>]`. Back up your `config.toml`, then change
headers such as `[profiles.local]` to `[local]`. Keep `default_profile` before the tables
and leave the profile fields unchanged. The initializer does not migrate existing files.
Verify the updated profile with the [API read example](#access-the-api-through-the-sdk).

### Migrate an INI Profile

SDK reads of `config.ini` are deprecated and emit `QDashConfigDeprecationWarning`, a
`FutureWarning`. The SDK uses INI only when the default TOML file is absent, or when an
explicit `.ini` path is supplied. It never merges the files or falls back after a TOML error.

To migrate, create `config.toml`, retain the `[local]` section name, and quote string
values as shown above. Rename `timeout_seconds` to `timeout_sec` and `retry_max_attempts` to
`read_attempts`. Write booleans as `true` or `false` and numeric settings without quotes.
Omit legacy client-only worker and backoff settings. Set `default_profile` if needed, then
verify the connection with `qdash.chips.list()`.

Existing `qdash-client` applications continue reading `config.ini` without this deprecation.
Keep that file if those applications still use it. Their `QDashConfig.save()` writes INI;
use `qdash config init` to create a new SDK TOML file. The existing-client example below
requires its own `local` INI profile.

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

qdash = QDash()
chips = qdash.chips.list()
print("Total:", len(chips))
for chip in chips:
    print(chip.chip_id, chip.qubit_count)
```

Create one client and reuse `qdash` across notebook cells or script operations. Each example
below includes initialization so it can run on its own; skip that line when reusing your client.
No `with` block or explicit `close()` is needed for this usage: the SDK closes its remaining
owned connections at normal Python process shutdown. To release a connection earlier, use
`qdash.close()` or a `with` block.
Closing the connection does not cancel work already dispatched to the server.

`qdash.chips.list()` returns chip metadata as a list; `qdash.chips.get(chip_id)` reads one
chip. `qdash.chip(chip_id)` creates a calibration handle without contacting the server.

`qdash.api` exposes the generated resources, grouped by API tags. Response types are available
from `qdash.sdk.types`. These calls use the client's authentication and project header,
perform no automatic retries by default, and raise generated `ApiError` subclasses or httpx
exceptions. SDK helpers such as `qdash.workflows.run()` translate failures to SDK errors;
HTTP 409 becomes `QDashConflictError`. Helper reads use `QDASH_RETRY_MAX_ATTEMPTS`; helper
writes are sent once. Do not enable retries on execution writes without reconciling their effects.

`qdash.with_project(project_id)` shares the connection and remains usable after the original
client variable is discarded. Explicitly closing the original owner closes the shared connection.
An externally supplied `httpx.Client` remains the caller’s responsibility. Token authentication
is preferred. Password authentication caches a login token; create a new client if it expires.

`QDash` clients and helpers are synchronous. The exported `AsyncQDashApi` is a separate
generated client: configure its base URL, authentication, and project explicitly; it does not
inherit a `QDash` client's configuration.

## Configure the Existing Client

For `qdash-client` and its `qdash-agent` command, put the following section in
`$XDG_CONFIG_HOME/qdash/config.ini` (default `~/.config/qdash/config.ini`).
Replace the URL, token, and project ID with those from your deployment. Keep the file
readable only by your user.

```ini
[local]
base_url = http://localhost:5714/api
api_token = <your-api-token>
project_id = your-project-id
```

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
from qdash.sdk import CalibrationSession, QDash
from qdash.calibration import CustomOneQubit, QubitTargets, TaskCall, sweep

client = QDash.from_profile("local")
session = CalibrationSession.create(client, chip_id="64Qv3", name="Coherence check")
print(session.session_id)  # Keep this ID to continue the same objective later.

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
check = session.validate(targets, steps, default_run_parameters=run_parameters)
if not check.valid:
    raise SystemExit(check.problems)

result = session.run(  # Measures and waits for completion.
    targets=targets,
    steps=steps,
    default_run_parameters=run_parameters,
    timeout_seconds=3600,
)
print(result.status, result.execution_ids)
```

`CalibrationSession` groups runs toward one objective on one chip. Creating it writes a record;
it neither reserves hardware nor starts measurements. Reuse `session` for additional trials.
`CalibrationSession.open(client, session_id="...")` reads an existing session without reopening
it if closed. `session.refresh()` reads its current record and runs.

`validate()` dispatches nothing. `run()` returns a `CalibrationResult` when the run completes;
a failed, cancelled, crashed, or unlaunched run raises `qdash.calibration.CalibrationRunError`
with the observed result in `error.result`. Completion does not mean every measured target
passed: inspect the executions and task results. A timeout raises `TimeoutError` without
cancelling the run or closing the session.

To keep a handle while work runs, use `launch = session.submit(targets, steps, ...)`, then
`launch.wait()`. `launch.get()` reads the current status and `launch.executions()` reads the
step executions. Keep the returned `run_id` and session ID to reconcile an interrupted wait.
Writes are sent once. Pass an `idempotency_key` to `run()` or `submit()` when a launch may need
to be retried; reconcile an uncertain response before starting another run.

Call `session.close()` when the objective is finished. Closing prevents new launches and does
not cancel work; the server can refuse closure while work remains. HTTP connection cleanup
does not close this group. Explicit sessions remain open until closed; automatic sessions
created by other launch APIs follow the [automatic closing rules](../../developer-guide/agent/calibration-sessions.md#closing).

Existing `chip.calibrate(targets, steps, ...)` and `chip.calibrate(pipeline)` remain available
and return their existing asynchronous handles. For a stored `Pipeline` from
`qdash.sdk.pipeline`, keep its name, tags, and defaults on that object; passing authoring
arguments alongside it raises `TypeError`. These older handles keep their existing failure-result
behavior; `CalibrationSession.run()` raises on an unsuccessful run.

### Inspect Step Outcomes

Targets, task calls and step classes come from `qdash.calibration`; their shared base is
`ExecutionStep` (the earlier `CalibrationStepDefinition` name remains an alias). Creating a
step only defines work; it sends no request.

`CalibrationResult.execution_ids` includes every reached step, including filters and schedules.
SDK `result.steps` maps each planned step's occurrence key to progress; a transform's
`transform` field contains its outcome. Keys use the calibration step ID or a unique transform
name, adding its plan position on collisions. An empty task list is normal for a transform.
In a workflow, typed calibration results stay in `result.steps`; transform snapshots are in
`result.details["transforms"]`, keyed by occurrence. Full per-step progress is available for
system pipeline runs; saved-workflow run handles list executions instead.

### Run a Whole Pipeline Spec

For a stored spec, use `qdash.pipelines.validate(spec, chip_id=...)` and
`qdash.pipelines.execute(spec, chip_id=...)`. The returned run's `wait()` returns the raw execution
detail. Read `detail.pipeline.status` for the whole pipeline when present and `detail.status` for
the individual execution. See [Pipeline specs](../../developer-guide/workflow/calibration-pipeline.md).

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

`WorkflowRun.get()` and `wait()` follow the recorded run and query Prefect for the whole
workflow state. They do not treat a completed first execution or a closed session as success.
`unknown` and `unavailable` are not terminal states; waiting retries until the timeout.
This requires a server with the calibration run state endpoint and a recorded run identity.
Older launches without that identity raise `RuntimeError` rather than report partial success.

Workflow handles and results now use `WorkflowRun` and `WorkflowRunResult`, rather than
subclasses of `Run` and `RunResult`. Update code that checks those base types.
`result.detail` is the first execution snapshot, or `None` if no execution exists yet;
`result.status`, `done`, and `succeeded` still describe the whole workflow.
`not_launched` ends the wait for a rejected attempt; a later explicit retry can launch it.

To cancel the whole workflow, keep its launch handle and use:

```python
run.cancel()
result = run.wait(timeout_seconds=600)
```

`cancel()` requires editor permission and returns `WorkflowCancellation` with the Prefect
`flow_run_id`, status, and message. `cancelling` acknowledges the request, not completion.
It sends one request and does not retry or wait. If the connection fails, check the run's
state before requesting cancellation again. A run that already ended raises
`QDashConflictError`. Other runs in the calibration session are not targeted.

Workflow, pipeline, and Workbench launches check hardware availability before creating a
session or run record. An existing conflicting lock returns `QDashConflictError` without
starting work or adding history. A successful same-key replay returns its saved response
without this check. If another request acquires the lock after the check, the final atomic
lock acquisition still prevents launch, but a rejected run record can remain.

## Follow an Existing Run

All SDK run handles display progress during `wait()` by default: the whole run's status,
time elapsed since waiting began, and available step or task counts. Notebooks and interactive
terminals update one display in place; redirected stderr logs only status or progress changes.
Terminal output goes to stderr. Pass `progress=False` to silence the display, including when
using `CalibrationSession.run()`. Interrupting the wait or reaching its timeout does not cancel
the remote run.

```python
from qdash.sdk import QDash

qdash = QDash.from_profile("local")
result = qdash.run("your-execution-id").wait(timeout_seconds=600)
print(result.status)
```

Replace the ID with one returned by an earlier launch. Creating the handle does not dispatch
work. Waiting follows the whole pipeline, returns failed or cancelled outcomes, and raises
`TimeoutError` without cancelling the run.

## List Executions and Task Results

```python
executions = qdash.executions.list(chip_id="64Qv3", date="2026-11-24", timezone="Asia/Tokyo")
results = qdash.task_results.list(chip_id="64Qv3", status="failed", task_name="CheckT1")
print(len(results), results.total)
records = results.to_records()
next_results = results.next_page()
```

Execution filters are chip and calendar day. Task result filters also include `qid`,
`execution_id`, `username`, `message_contains`, `step_id`, `call_id`, and the inclusive
`start_from` / `start_to` bounds (timezone-aware datetimes). Both return newest-first pages;
`skip` starts at 0 and `limit` accepts 1–100. Iteration and conversions use only the loaded
page. `next_page()` retains filters and returns None at the end. New records can shift these
offset-based pages. Execution `total` and `has_next` can be None when the server omits totals.
`results.status_counts` covers all pages with the other filters applied, ignoring `status`.

`to_dataframe()` needs pandas; `to_records()` needs no extra package. In a notebook, display
`results.to_dataframe()[["start_at", "task_name", "qid", "status", "task_id"]]` for a compact
table. The table contains only the loaded page. Read full details with
`qdash.execution(row.execution_id).get()` or `qdash.task_result(row.task_id)`.

## Inspect Execution Results

`WorkflowRun.get()` and `wait()` report the whole workflow. A handle from
`qdash.run(execution_id)` follows that execution and its pipeline progress, not an arbitrary
workflow containing multiple executions. `run.executions()` reads each started
execution in step order; each returned `ExecutionResult.status` is that execution's own
status. Pending steps without an execution ID are omitted.

```python
run = qdash.run("your-execution-id")
for execution in run.executions():
    print(execution.execution_id, execution.name, execution.status)
    for task in execution.tasks:
        print(task.task_id, task.name, task.qid, task.status, task.message)
        print("run:", task.run_parameters)
        for name, parameter in task.output_parameters.items():
            if parameter is not None:
                print(name, parameter.value, parameter.unit)
```

`task.input_parameters` and `task.output_parameters` retain parameter metadata, including
units and reported errors, in a read-only `Parameters` mapping. Each `Parameter` displays
only its value, unit, and error; properties such as `calibrated_at` and `task_id`, plus
`metadata`, retain the details. A parameter reported as null stays `None`. Display
`task.input_parameters.to_dataframe()` or `task.output_parameters.to_dataframe()` to inspect
them as tables. Use `task_id` or `invocation` to distinguish repeated calls.
To read one execution, use `qdash.execution(execution_id).get()`. To read the full saved task
result, including any `stack_trace`, use `qdash.task_result(task_id)` or `task.get()`.
These are snapshots; fetch them again to see updates. `detail` retains the original response.

In a notebook, display a task's figures explicitly:

```python
task = qdash.task_result("your-task-id")
for figure in task.figures:
    figure.show()
# Save a selected figure to an explicit local filename:
# task.figures[0].save("t1.png")
```

`show()` needs IPython. Figures, `task.json_figures`, and `task.raw_data` also provide
`read()` for bytes and `save(path, overwrite=False)`. Each call fetches the file through the
session; inspecting or printing a handle does not. Saving requires an existing parent directory
and refuses an existing file unless `overwrite=True`. Missing server files raise
`QDashNotFoundError`. Keep the session open while fetching results and files.

## Run a Task from the Workbench

`qdash.tasks` uses the Task Workbench's catalog and single-task execution route. Inspect a
definition's `input_parameters`, `run_parameters`, and `output_parameters` before choosing
settings; `qdash.tasks.list(enabled_only=True)` lists runnable definitions. Pass
`backend_name` if the server has no configured default backend.

```python
from qdash.sdk import QDash
from qdash.calibration import TaskCall, sweep

qdash = QDash.from_profile("local")
definition = qdash.tasks.get("CheckT1")
print(definition.run_parameters)
call = TaskCall(
    name="CheckT1",
    run={"time_range": sweep.linspace(300, 500_000, 51)},
    update_calibration_parameters=False,
)
run = qdash.tasks.run(call, chip_id="64Qv3", qid="0")  # measures
result = run.wait(timeout_seconds=600)
print(result.status)
for task in run.results():
    print(task.task_id, task.status, task.output_parameters)
```

Use a chip, target, and measurement settings appropriate for your hardware. `TaskCall` is
the same definition accepted by `CustomOneQubit(tasks=[call])`: `run` supplies measurement
settings and `input` overrides calibration inputs. Single-task execution rejects `call_id`
and `on_failure`, which apply within pipeline steps. Set call parameters on `TaskCall`, not
as duplicate arguments to `tasks.run()`.

To load current inputs and run defaults before building a call:

```python
params = qdash.tasks.load_parameters("CheckT1", chip_id="64Qv3", qid="0")
print(params.input, params.run, params.missing)
params.run["time_range"] = sweep.linspace(300, 500_000, 51)
call = params.to_call()
```

Loading only reads data. `to_call()` rejects unknown names, missing required inputs, and
edits to `params.forbidden` inputs; forbidden values remain visible but are omitted from
the call. Fill missing editable inputs, or calibrate missing forbidden values first.
`params.unresolved` lists inputs with resolution rules the SDK does not recognize; these
are left to the worker. Values and bounds are still validated when the task runs.
Loaded inputs are target-specific: use the same chip, qid, and backend when running the call.
Reload to see newer calibration values. For a multi-target pipeline, define a `TaskCall`
without these input overrides so each target resolves its own values.

By default, a single-task run records history and artifacts without replacing current
calibration values. Set `TaskCall(update_calibration_parameters=True, ...)` to replace them
with validated outputs. `reconfigure` and `update_params` also default to false. This default
is specific to single-task runs; pipeline calls with an unset update policy inherit it.
`source_task_id` records provenance; it does not restore historical inputs. Execution uses
current task definitions and calibration state.

`run.results()` reads all matching task/target results, excluding setup tasks, and may be
empty before results arrive. Use `run.executions()` to include all tasks. A timeout does not
cancel execution; reattach with `qdash.run(run.execution_id)`. Writes send once; after an
uncertain response, reconcile before repeating. Supply the same `idempotency_key` and request
when retrying a launch; `calibration_session_id` groups it with an existing open session.

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

For topology JSON/PNG and Qubex configuration downloads, follow
[Export Device Gateway Files](../../user-guide/device-gateway-export.md).

## Agent Calibration

`AgentCalibrationRunner` runs a bounded step; `AgentPlanRunner` runs an approved graph.
Neither creates approval implicitly. Follow [Agent Calibration](../../user-guide/agent-calibration.md)
for session scope, candidate review, and expert intervention.

## Use the Low-Level Client

For existing `qdash-client` applications, use `qdash.client.rest` only when a high-level method is unavailable. High-level methods share
authentication, project headers, retries, and validation.
