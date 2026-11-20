# Python SDK

`qdash.sdk` lets a Python script define a [calibration pipeline](../workflow/calibration-pipeline.md)
as objects and validate or run it through the QDash API. It ships in the `qdash-client`
distribution beside `qdash.client`; the user-facing example is in the
[Python Client reference](../../reference/clients/python.md#define-and-run-a-calibration-pipeline).

## Responsibility boundary

| Layer | Owns | Leaves to others |
| --- | --- | --- |
| `qdash.client` (`QDashClient`) | Configuration and profiles, authentication, `X-Project-Id`, HTTP transport, retries, error mapping, one method per route, generated response models | Building request bodies from domain objects |
| `qdash.sdk` | The `QDash` session and its client ownership, pipeline definition objects, their serialization to spec version 2, the run handle | Transport, auth, retries, any check that needs server data |
| API | Permissions, the step and task catalog, calibration data, preflight, dispatch | Anything on the author's machine |

The SDK keeps no state between calls beyond the objects the author holds: no cache of the
catalog, no registry of runs, no local plan of what the server will do.

## Define, check, run

Every operation belongs to one phase, and no phase starts the next one implicitly.

| Phase | Calls | Effects | Route |
| --- | --- | --- | --- |
| Define | `Pipeline(...)`, `CustomOneQubit(...)`, `Pipeline.to_spec()` | None; no network | None |
| Check | `qdash.pipelines.validate(pipeline, chip_id=...)` | None; the server reports problems as data | `POST /calibration-pipelines/validate` |
| Run | `qdash.pipelines.execute(pipeline, chip_id=...)`, then `run.wait()` | Dispatches one execution that claims the hardware | `POST /calibration-pipelines/execute`, `GET /executions/{id}` |

`execute` does not call `validate` first; the server validates the spec again before dispatch
and answers 422 with the same problem list. `execute` refuses to send a request when the
session has no `project_id`, so a run never falls back to the user's default project.
`qdash.pipelines.catalog()` (`GET /calibration-pipelines/catalog`) returns the step types and
task names a spec may use.

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

`qdash.sdk.pipeline` adds only conveniences on top of the generated models:

| Name | Generated base | Adds |
| --- | --- | --- |
| `Pipeline` | `CalibrationPipelineSpec` | `spec_version` fixed to 2, `to_spec()` |
| `Qubits` | `PipelineTargets` | Positional list of qubit IDs |
| `CustomOneQubit` | `CustomOneQubitStep` | `type` filled in |
| `TaskCall` | `TaskCall` | Plain-string `call_id` and `on_failure` for type checkers |
| `sweep` | None | `{"value": [...], "value_type": ...}` declarations, as `qdash.workflow.sweep` writes them |

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

`QDash.from_env()` and `QDash.from_profile()` create a `QDashClient` that the session owns and
closes on exit. `QDash(client)` uses the caller's client and never closes it.
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

`ExecutePipelineResponse.execution_id` falls back to the Prefect flow run ID when the API could
not pre-create the execution; `wait()` then polls that ID until the timeout if no execution has it.

## Packaging

`qdash` is an implicit namespace package shared by the root project (`src/qdash/`) and
`qdash-client` (`clients/python/src/qdash/`); no distribution ships `qdash/__init__.py`. The
wheel contains `qdash.client` and `qdash.sdk` and depends only on `httpx` and Pydantic, so the
SDK installs without Prefect, qubex, NumPy or pint. `qdash.sdk` is unrelated to
`qdash.api.metric_runtime.sdk`, the server-side module metric scripts import as `qdash_metrics`.

Python flows written against `qdash.workflow` remain the way to express loops, conditions on
results or steps outside the catalog; the SDK does not convert them.

## Tests

| Test | Covers |
| --- | --- |
| `clients/python/tests/test_sdk_pipeline.py` | Serialized spec, call order and IDs, local structural checks, sweep wire format, literal types against the generated enums |
| `clients/python/tests/test_sdk_session.py` | Requests and headers through `httpx.MockTransport`, explicit execute, whole-pipeline wait and timeout, 403 and 422 propagation, client ownership, project scope |
| `clients/python/tests/test_sdk_wheel.py` | Builds the wheel, installs it into a fresh environment, and imports both namespaces without server packages |
| `tests/qdash/api/routers/test_calibration_pipeline_sdk.py` | The example against the real routes and server spec model, including preflight problems and sweep parity with `qdash.datamodel.sweep` |
| `tests/qdash/api/test_app_factory.py` | The published components and the refusal to replace a different model under a taken name |

## Implementation Files

- `clients/python/src/qdash/sdk/_session.py`: `QDash`.
- `clients/python/src/qdash/sdk/_pipelines.py`: `Pipelines`, `PipelineRun`.
- `clients/python/src/qdash/sdk/pipeline.py`, `sweep.py`: definition objects and sweeps.
- `clients/python/src/qdash/client/services/client.py`: the pipeline route methods and `with_project`.
- `src/qdash/api/app/factory.py`: `OPENAPI_COMPONENT_MODELS`.
