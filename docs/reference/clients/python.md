# Python Client

`qdash-client` provides typed, high-level access to QDash for scripts, notebooks, exporters, and
agent integrations. It supports Python 3.11 and 3.12.

## Install the Package

```bash
pip install qdash-client
```

`qdash-client` provides `qdash.client`, one method per API route. To also define and run
[calibration pipelines](#define-and-run-a-calibration-pipeline) with `qdash.sdk`, install
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
| Agent calibration | Sessions, actions, candidate gates, commits, apply operations, and polling helpers |

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

## Define and Run a Calibration Pipeline

`qdash.sdk`, from the `qdash-sdk` package, builds a [calibration pipeline spec](../../developer-guide/workflow/calibration-pipeline.md)
from Python objects, validates it on the server, and runs it only when asked. This pipeline runs
`Configure`, `CheckT1` and `CheckT2Echo` on qubits 0 and 1:

```python
import math

from qdash.sdk import QDash
from qdash.sdk.pipeline import CustomOneQubit, Pipeline, Qubits, TaskCall, sweep

time_range = sweep.logspace(math.log10(300), math.log10(500_000), 51)
pipeline = Pipeline(
    name="coherence-t1-t2echo",
    targets=Qubits(["0", "1"]),
    steps=[
        CustomOneQubit(
            step_name="coherence",
            tasks=[
                TaskCall(name="Configure"),
                TaskCall(name="CheckT1", run={"time_range": time_range}),
                TaskCall(name="CheckT2Echo", run={"time_range": time_range}),
            ],
        ),
    ],
    default_run_parameters={"readout_duration": 1024, "interval": 262_144},
)

with QDash.from_env() as qdash:
    result = qdash.pipelines.validate(pipeline, chip_id="64Qv3")  # no effects
    if not result.valid:
        raise SystemExit([f"{p.path}: {p.message}" for p in result.problems or []])
    run = qdash.pipelines.execute(pipeline, chip_id="64Qv3")  # dispatches and measures
    detail = run.wait(timeout_seconds=3600)
    print(detail.pipeline.status if detail.pipeline else detail.status)
```

| Call | Result |
| --- | --- |
| `Pipeline(...)`, `pipeline.to_spec()` | The spec version 2 JSON object; nothing is sent |
| `qdash.pipelines.catalog(backend_name=None)` | Step types, task names by type, and the spec schema |
| `qdash.pipelines.validate(pipeline, chip_id=...)` | `ValidatePipelineResponse`; problems are data, not exceptions |
| `qdash.pipelines.execute(pipeline, chip_id=...)` | `PipelineRun`; raises `QDashValidationError` (422) for a spec with problems and `QDashConfigError` without a project |
| `run.wait(timeout_seconds=3600, poll_interval_seconds=5)` | The execution detail once the whole pipeline ends; `TimeoutError` otherwise |

Building a pipeline checks only its structure, such as required fields, ID patterns and literal
values. The server decides whether it can run, including task names, repeated call IDs and the
calibration data each task needs, so pass a pipeline through `validate` before `execute`. A
valid result is not a hardware safety check beyond those rules.

`QDash.from_env()` and `QDash.from_profile(...)` read the same settings as `QDashClient` and
close their client on exit. `QDash(client)` uses an existing client and leaves it open.
`project_id=...` on any of them scopes the session to another project without changing the
client's configuration. Other step types are passed as their generated models from
`qdash.client.services.models` or as dictionaries in the spec's JSON form. How the SDK is built:
[Python SDK](../../developer-guide/architecture/python-sdk.md).

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
[Agent Calibration](../../user-guide/agent-calibration.md).

## Use the Low-Level Client

`qdash.client.rest` exposes the generated transport for operations that do not yet have a
high-level method. Prefer `QDashClient` when a high-level method exists because it supplies shared
authentication, project headers, retries, response validation, and error mapping.
