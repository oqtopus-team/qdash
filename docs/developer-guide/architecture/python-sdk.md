# Python SDK

`qdash.sdk` lets a Python script define a calibration as objects and validate or start it on a
chip through the QDash API; each one runs as a [calibration pipeline](../workflow/calibration-pipeline.md).
It ships in the `qdash-sdk` distribution, which depends on `qdash-client`; the user-facing
example is in the [Python Client reference](../../reference/clients/python.md#run-a-calibration).

## Responsibility boundary

| Layer | Owns | Leaves to others |
| --- | --- | --- |
| `qdash.client` (`QDashClient`) | Configuration and profiles, authentication, `X-Project-Id`, HTTP transport, retries, error mapping, one method per route, generated response models | Building request bodies from domain objects |
| `qdash.sdk` | The `QDash` session and its client ownership, the `Chip` front door, the `Workflows` front door to registered workflows, definition objects, their serialization to spec version 2, the run handles | Transport, auth, retries, any check that needs server data |
| API | Permissions, the step and task catalog, calibration data, preflight, dispatch | Anything on the author's machine |

The SDK keeps no state between calls beyond the objects the author holds: no cache of the
catalog, no registry of runs, no local plan of what the server will do.

## Define, check, run

Every operation belongs to one phase, and no phase starts the next one implicitly.

| Phase | Calls | Effects | Route |
| --- | --- | --- | --- |
| Define | `qdash.chip(...)`, `QubitTargets(...)`, `CustomOneQubit(...)`, `Pipeline(...)`, `Pipeline.to_spec()` | None; no network | None |
| Check | `chip.validate_calibration(targets, steps)`, `qdash.pipelines.validate(pipeline, chip_id=...)` | None; the server reports problems as data | `POST /calibration-pipelines/validate` |
| Run | `chip.calibrate(targets, steps)`, `qdash.pipelines.execute(pipeline, chip_id=...)`, then `run.wait()` | Dispatches one execution that claims the hardware | `POST /calibration-pipelines/execute`, `GET /executions/{id}` |
| Inspect a registered workflow | `qdash.workflows.list()`, `qdash.workflows.get(name)` | None; reads stored metadata and source | `GET /flows`, `GET /flows/{name}` |
| Run a registered workflow | `workflow.run(parameters=...)`, `qdash.workflows.run(name, parameters=...)`, then `run.wait()` | Dispatches the saved deployment | `POST /flows/{name}/execute`, `GET /executions/{id}` |

`Chip` is a front door over `Pipelines`, not a second implementation:
`validate_calibration` and `calibrate` build a `Pipeline` from `targets`, `steps` and the
`name`, `default_run_parameters` and `tags` given, and call `Pipelines.validate` and
`Pipelines.execute` with the chip's ID. `calibrate` does not call `validate_calibration`
first, and `execute` does not call `validate`; the server validates the spec again before
dispatch and answers 422 with the same problem list. `execute` refuses to send a request when
the session has no `project_id`, so a run never falls back to the user's default project.
`qdash.pipelines.catalog()` (`GET /calibration-pipelines/catalog`) returns the step types and
task names a spec may use.

`Workflows` reaches flows that were saved, with a deployment and a target chip, from the UI
or `QDashClient.save_flow`. It wraps `list_flows`, `get_flow` and `execute_flow` and adds two
checks before any request: a name that does not match the server's flow name rule
(`[A-Za-z0-9_]+`) raises `ValueError` instead of becoming a request path, and `run` refuses to
send without a `project_id`, as `execute` does. `run` always sends a `parameters` object (`{}`
when none are given), which the server merges over the saved `default_parameters`. The server
runs the flow on its saved `chip_id` unless the merged parameters carry a `chip_id`; the SDK adds
no chip selection and no `target_override`. `Workflow.default_parameters` is the saved defaults,
not a description of the parameters the flow function accepts. Registering a workflow stays
with `save_flow`.

Importing a module that builds pipelines writes nothing and measures nothing. The SDK never
imports or executes flow source locally; a spec cannot reference code.

## Shared models

The pipeline classes come from the API's own models. `CalibrationPipelineSpec` in
`src/qdash/datamodel/calibration_pipeline.py` is published as an OpenAPI component by
`_add_component_models` in `src/qdash/api/app/factory.py`, so `task generate` writes
`CalibrationPipelineSpec`, `PipelineTargets`, `TaskCall` and one model per step type into
`clients/python/src/qdash/client/services/models.py`. The request field
`ValidatePipelineRequest.spec` stays a plain JSON object: a typed body would make FastAPI answer
422 before the validate route can report path-specific problems or migrate a version 1 spec.

`qdash.sdk.pipeline` adds only conveniences on top of the generated models, and
`qdash.sdk.calibration` re-exports the same classes, without `Pipeline`, for `Chip`:

| Name | Generated base | Adds |
| --- | --- | --- |
| `Pipeline` | `CalibrationPipelineSpec` | `spec_version` fixed to 2, `to_spec()` |
| `QubitTargets` (also `Qubits`) | `PipelineTargets` | Positional list of qubit IDs |
| `MuxTargets` | `PipelineTargets` | Positional MUX IDs and `exclude_qids` |
| `CustomOneQubit` | `CustomOneQubitStep` | `type` filled in |
| `TaskCall` | `TaskCall` | Plain-string `call_id` and `on_failure` for type checkers |
| `sweep` | None | `{"value": [...], "value_type": ...}` declarations, as `qdash.workflow.sweep` writes them |

The target and step names match `qdash.workflow`'s `QubitTargets`, `MuxTargets` and
`CustomOneQubit`, but they are separate serializable classes: the workflow classes resolve
targets and run tasks inside the worker, and importing them would pull in Prefect and qubex.
Other step types are passed as their generated models or as dictionaries in the spec's JSON form.
`to_spec()` writes only the fields the author set, plus `spec_version` and each step's `type`,
so server defaults apply to everything else. A mapping passed to `validate` or `execute` is sent
unchanged.

Local validation is structural: required fields, ID patterns, literal values, list lengths and
`extra="forbid"` from the generated schema. Rules that live in Pydantic validators, such as
unique call IDs, step order and target exclusivity, and everything that reads calibration data,
are checked only by the server. A pipeline that builds locally can still be invalid; for example,
`CheckT1` on a qubit without Rabi parameters is a validate problem.

## Session and client ownership

`QDash.from_env()` and `QDash.from_profile()` create a `QDashClient` that the session owns;
`QDash.close()`, or leaving a `with` block, closes it. `QDash(client)` uses the caller's client
and never closes it. The session holds no other resource: `QDash.chip()` returns a `Chip` that
shares the session's `Pipelines` and client, and `QDash.workflows` shares the same client, so every chip and call of one session uses one
connection and one project, and nothing is closed by garbage collection.
`QDash(client, project_id=...)` calls `QDashClient.with_project`, which returns a copy that
shares the caller's connection and credentials but sends the other project; the caller's client
and configuration are unchanged, and closing the copy leaves the shared connection open.
`QDash.client` exposes the underlying client for routes the SDK does not wrap.

## Following a run

`PipelineRun.wait()` calls `QDashClient.wait_for_execution` with `whole_pipeline=True`. It polls
`GET /executions/{execution_id}` until `pipeline.status`, or the execution's own `status` when
the server reports no pipeline progress, is terminal; see
[Following a run](../workflow/calibration-pipeline.md#following-a-run). An execution that is not
listed yet (404) is polled again. A failed or cancelled run is returned, and `TimeoutError` is
raised after `timeout_seconds` without cancelling the run.

`CalibrationRun.wait()` calls `PipelineRun.wait()`, and `WorkflowRun.wait()` calls
`wait_for_execution` with the same arguments. Both return a `RunResult` that holds the same
`ExecutionResponseDetail` as `detail` and the run's `execution_id`. Its `status` property reads
`detail.pipeline.status`, falling back to `detail.status` exactly as the wait does, so a run whose
first step completed and whose later step failed reports `failed`. `PipelineRun.wait()` keeps
returning the raw detail.

`ExecutePipelineResponse.execution_id` and `ExecuteFlowResponse.execution_id` fall back to the Prefect flow run ID when the API could
not pre-create the execution; `wait()` then polls that ID until the timeout if no execution has it.

## Packaging and release

`qdash` is an implicit namespace package shared by three distributions, and none of them ships
`qdash/__init__.py`:

| Distribution | Source | Wheel contents | Runtime dependencies |
| --- | --- | --- | --- |
| `qdash` (server, not published) | `src/qdash/` | Server packages | Server stack |
| `qdash-client` | `clients/python/` | `qdash/client/` only | `httpx`, Pydantic |
| `qdash-sdk` | `sdks/python/` | `qdash/sdk/` only | `qdash-client` of the same version |

Neither published wheel installs a file of the other, so uninstalling `qdash-sdk` leaves
`qdash.client` working, and uninstalling `qdash-client` leaves `qdash.sdk` installed but
unimportable. The SDK installs without Prefect, qubex, NumPy or pint. `qdash.sdk` is unrelated
to `qdash.api.metric_runtime.sdk`, the server-side module metric scripts import as
`qdash_metrics`.

Both packages take their version from hatch-vcs with the same settings and receive the release
version through `SETUPTOOLS_SCM_PRETEND_VERSION`. The custom metadata hook in
`sdks/python/hatch_build.py` reads the version being built and writes the SDK's only
dependency:

| Built version | `Requires-Dist` |
| --- | --- |
| `X.Y.Z` (QDash tag) or `X.Y.ZbN` (develop beta) | `qdash-client==<version>` |
| A hatch-vcs development version such as `1.0.13.post1.dev1282`, or `0.0.0` | `qdash-client` |

Development versions change on every commit and name no published client, so leaving them
unpinned keeps `uv.lock` stable; the workspace resolves `qdash-client` to `clients/python`
through `[tool.uv.sources]`. Because the dependency is dynamic, `uv lock` and
`uv sync --locked` build the SDK's metadata, so every Dockerfile that copies workspace
member manifests also copies `sdks/python/hatch_build.py`.

`.github/workflows/publish-qdash-client.yml` builds both packages from one release record,
publishes `qdash-client`, and then publishes `qdash-sdk`; the release pipeline is described in
[Pi Packages](../copilot/packages.md#distribution). The workflow keeps its filename because
the existing `qdash-client` PyPI Trusted Publisher names it.

Python flows written against `qdash.workflow` remain the way to express loops, conditions on
results or steps outside the catalog; the SDK does not convert them.

## Tests

| Test | Covers |
| --- | --- |
| `sdks/python/tests/test_sdk_pipeline.py` | Serialized spec, call order and IDs, local structural checks, sweep wire format, literal types against the generated enums |
| `sdks/python/tests/test_sdk_calibration.py` | Re-exported definitions and target serialization, `Chip` binding without requests, validate against calibrate effects, whole-run `status` and raw `detail`, project scope shared by chips |
| `sdks/python/tests/test_sdk_workflows.py` | `list` and `get` mapping and project scope, 404, name checks before any request, no dispatch until `run`, parameter forwarding including `{}`, whole-run `status`, pending 404 and timeout, shared client lifecycle |
| `sdks/python/tests/test_sdk_session.py` | Requests and headers through `httpx.MockTransport`, explicit execute, whole-pipeline wait and timeout, 403 and 422 propagation, client ownership, project scope |
| `sdks/python/tests/test_sdk_distributions.py` | Builds both packages at a stable and a beta version, checks the `qdash-client` pin and disjoint wheels, and installs and uninstalls them in fresh environments |
| `tests/qdash/api/routers/test_calibration_pipeline_sdk.py` | The calibration and pipeline examples against the real routes and server spec model, including both target kinds, preflight problems, 403 and 422, and sweep parity with `qdash.datamodel.sweep` |
| `tests/qdash/api/routers/test_workflows_sdk.py` | `QDash.workflows` against the real `/flows` routes: project scoping, saved defaults merged with run parameters, no dispatch from `list` or `get` |
| `tests/qdash/api/test_app_factory.py` | The published components and the refusal to replace a different model under a taken name |

## Implementation Files

- `sdks/python/src/qdash/sdk/_session.py`: `QDash`.
- `sdks/python/src/qdash/sdk/_calibration.py`: `Chip`, `CalibrationRun`.
- `sdks/python/src/qdash/sdk/_workflows.py`: `Workflows`, `Workflow`, `WorkflowRun`.
- `sdks/python/src/qdash/sdk/_runs.py`: `RunResult`.
- `sdks/python/src/qdash/sdk/_pipelines.py`: `Pipelines`, `PipelineRun`.
- `sdks/python/src/qdash/sdk/pipeline.py`, `sweep.py`: definition objects and sweeps.
- `sdks/python/src/qdash/sdk/calibration.py`: the definitions `Chip` takes, re-exported.
- `sdks/python/hatch_build.py`: the `qdash-client` pin.
- `clients/python/src/qdash/client/services/client.py`: the pipeline and flow route methods and `with_project`.
- `src/qdash/api/app/factory.py`: `OPENAPI_COMPONENT_MODELS`.
