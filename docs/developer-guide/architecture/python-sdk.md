# Python SDK

`qdash.sdk` lets a Python script define a calibration as objects and validate or start it on a
chip through the QDash API; each one runs as a [calibration pipeline](../workflow/calibration-pipeline.md).
It also saves [metric scripts](./metric-scripts.md) and [dashboards](./dashboards.md)
defined in Python.
It ships in the `qdash-sdk` distribution, which depends on `qdash-client`; the user-facing
example is in the [Python Client reference](../../reference/clients/python.md#run-a-calibration).
TypeScript applications use the separate `@oqtopus-team/qdash-sdk` package, described in
[TypeScript SDK](./typescript-sdk.md).

## Responsibility boundary

| Layer | Owns | Leaves to others |
| --- | --- | --- |
| `qdash.client` (`QDashClient`) | Configuration and profiles, authentication, `X-Project-Id`, HTTP transport, retries, error mapping, one method per route, generated response models | Building request bodies from domain objects |
| `qdash.sdk` | The `QDash` session and its client ownership, the `Chip` front door, the `Workflows` front door to registered workflows, definition objects, their serialization to spec version 2, the run handles, the `Script` and `Dashboard` definitions and their saved handles | Transport, auth, retries, any check that needs server data |
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
| Author metric scripts and dashboards | `Script(...)`, `Dashboard(...)`, then `qdash.scripts.create`/`update`, `qdash.dashboards.create`/`update` | Saves a script revision or a dashboard | `/metric-scripts`, `/dashboards` |

`Pipelines.execute` and `Workflows.run` (and `Workflow.run`) take optional
`calibration_session_id` and `idempotency_key`. The server records the run in that calibration
session, or in an automatic one it creates, before it is launched; a retry with the same key
returns the recorded run, and without a key every call starts a new run. `WorkflowRun` exposes
`calibration_session_id` and `calibration_run_id`. When either argument is given, a response
that does not name the recorded run raises `RuntimeError`: an older server may have started the
run without them, so reconcile it instead of retrying. For a workflow whose chip the server
cannot tell before the launch (no `chip_id` parameter and no saved chip), the server refuses
either argument with 400 and starts nothing; pass `chip_id` in `parameters`. With a session, an optional `decision_id` names the session's decision the run
carries out; without `calibration_session_id` it raises `ValueError` before any request. A
response that does not echo the `decision_id` raises `RuntimeError` instead of returning, since
the run may have started without the link: reconcile it in the session audit, never retry with a
new key. See [Calibration Sessions](../agent/calibration-sessions.md).

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

## Metric scripts and dashboards

`qdash.sdk.dashboard` defines a metric script and a dashboard locally;
`QDash.scripts` and `QDash.dashboards` save them. Two Python APIs are involved and must not be
confused: a metric script's source is written against `qdash_metrics`, which exists only in the
metric worker (`src/qdash/api/metric_runtime/sdk.py`) and computes cells; `qdash.sdk` treats
that source as text and only authors and saves it remotely. The SDK never imports, executes or
parses the source. `Script.from_file` reads it as UTF-8, and the server's validation on save
returns the metric catalog.

```python
from qdash.sdk import Dashboard, QDash, Script

qdash = QDash.from_env(project_id="my-project")
script = qdash.scripts.create(Script.from_file("zx90_median.py", visibility="project"))
zx90 = script.metric("zx90_median")  # ScriptMetric pinned to script.revision

board = Dashboard("ZX90 health", visibility="project", chip_id="64Qv3")
board.add_metric(zx90, period=14, params={"min_samples": 3})
saved = qdash.dashboards.create(board)
print(saved.dashboard_id)
```

A save returns a `SavedScript` bound to one revision: after `create` or `update` the revision
that save produced, or kept when the source equals the latest saved source (the server adds no
revision then); after `get` the active revision unless `revision=` names another.
`SavedScript.metric(id)` looks the metric up in that revision's catalog and raises
`MetricScriptError`, naming the script ID and revision, when the revision is invalid or does not
declare the metric. An invalid save therefore never yields a panel silently pinned to the older
active revision. `qdash.scripts.template(id)` reads a starter template's source into a local
`Script`; `qdash.scripts.validate` compiles source without saving it.

`Dashboard.add_metric` builds a `metric_script` panel from a `ScriptMetric`, with a config of the
generated `MetricScriptPanelConfig` model; `add_markdown` adds a note. The builder follows the
dashboard editor's rules in `ui/src/components/features/dashboards/layout.ts`: a new
panel goes to the left edge below every panel, 6 by 4 for a metric and 12 by 2 for a note.
`hops` defaults to the metric's declared distances, `period` to the last 14 days. `view`
defaults to `map` for a scalar metric and `timeseries` for a series metric
(`ScriptMetric.result == "series"`); a series metric needs `targets` (1 to 16 cell keys), and
`add_metric` raises `ValueError` for a view or targets that do not fit the metric, as the server
would on save. A scalar panel's config has no `targets` key, so it stays valid on servers from
before series metrics, whose config model forbids unknown keys:

```python
trend = qdash.scripts.create(qdash.scripts.template("zx90_daily_trend")).metric("zx90_daily_trend")
board.add_metric(trend, period=28, targets=["0>1", "1>0"], params={"interval": "week"})
```
 Panel IDs are
derived from the metric ID (`zx90_median`, then `zx90_median-2`), so rerunning a script produces
the same IDs. An explicit `layout=(x, y, w, h)` or `panel_id=` overrides the default. The server
still validates every panel on save.

Updates name their target by ID or by a saved handle, and the SDK never matches by name, keeps
local state, retries a write or rolls back earlier steps; a failure in a multi-step script
leaves what was saved, and the IDs are on the returned handles and in `MetricScriptError`.
`qdash.scripts.update(saved, script)` sends `expected_revision` from the handle.
`qdash.dashboards.update(target, board)` replaces the dashboard's settings and panels and sends
`expected_version`: the version of a `SavedDashboard` target, or for an ID the version read just
before saving. The server answers 409 when the dashboard changed since that version.
`SavedDashboard.edit()` returns a `Dashboard` with the stored panels for a read-edit-save.
Settings left as `None` (`description`, `visibility`, `chip_id`) are not sent, so the SDK cannot
clear a dashboard's chip. These calls need no configured project: like the UI, they use the
session's project or the user's default, and the server applies its own permissions.

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

The generated models follow the published schema, so a server field's schema decides how a
client that dumps every field behaves. An optional field that rejects `null` needs a plain
`default` (`Field(default=[])`), not `default_factory`, which Pydantic leaves out of the JSON
schema; without a published default the generator types the field as nullable and the client
accepts `None` that the server rejects. A field whose server default depends on other fields,
such as `max_parallel_ops` on two-qubit steps, is published as nullable with `null` meaning
unset, and the server model's serializer keeps its own dumps unchanged.

Local validation is structural: required fields, ID patterns, literal values, list lengths and
`extra="forbid"` from the generated schema. Rules that live in Pydantic validators, such as
unique call IDs, step order and target exclusivity, and everything that reads calibration data,
are checked only by the server. A pipeline that builds locally can still be invalid; for example,
`CheckT1` on a qubit without Rabi parameters is a validate problem.

## Extending the SDK

Change the contract on the server first, so the SDK, the generated clients and the published
schema cannot disagree:

1. Add or change the field or step model in `src/qdash/datamodel/calibration_pipeline.py`,
   with a `description` that states the rules its validators enforce.
2. Run `task generate` to rewrite `docs/oas/openapi.json`,
   `clients/python/src/qdash/client/services/models.py` and the TypeScript clients; never edit
   them by hand.
3. Add a convenience in `qdash.sdk.pipeline` only when the generated model is awkward to write,
   such as a positional argument or a fixed `type`, and keep it a subclass of the generated
   model.
4. Test that the generated model, `to_spec()` and a plain `model_dump(mode="json")` are
   accepted or rejected by the server model as intended, in
   `tests/qdash/api/routers/test_calibration_pipeline_sdk.py`, and add SDK-only behavior to
   `sdks/python/tests/`.

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
[Pi Packages](../agent/packages.md#distribution). The workflow keeps its filename because
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
| `tests/qdash/api/routers/test_calibration_pipeline_sdk.py` | The calibration and pipeline examples against the real routes and server spec model, including both target kinds, preflight problems, 403 and 422, sweep parity with `qdash.datamodel.sweep`, and generated two-qubit steps serialized by `to_spec()` and by a plain dump |
| `tests/qdash/api/routers/test_workflows_sdk.py` | `QDash.workflows` against the real `/flows` routes: project scoping, saved defaults merged with run parameters, no dispatch from `list` or `get` |
| `sdks/python/tests/test_sdk_dashboards.py` | No requests or execution while defining, panel IDs, layouts, hops and config, revision binding and `MetricScriptError`, request bodies with only the given fields, `expected_revision` and `expected_version`, 409 propagation |
| `tests/qdash/api/routers/test_sdk_dashboard_routes.py` | The ZX90 median and collision grid dashboards against the real routes and in-process metric runtime, stale-version 409, unchanged and invalid script saves, 403 and 422, project scope |
| `tests/qdash/api/test_app_factory.py` | The published components, the refusal to replace a different model under a taken name, and no cached schema after a failed transformation |

## Implementation Files

- `sdks/python/src/qdash/sdk/_session.py`: `QDash`.
- `sdks/python/src/qdash/sdk/_calibration.py`: `Chip`, `CalibrationRun`.
- `sdks/python/src/qdash/sdk/_workflows.py`: `Workflows`, `Workflow`, `WorkflowRun`.
- `sdks/python/src/qdash/sdk/_runs.py`: `RunResult`.
- `sdks/python/src/qdash/sdk/_pipelines.py`: `Pipelines`, `PipelineRun`.
- `sdks/python/src/qdash/sdk/pipeline.py`, `sweep.py`: definition objects and sweeps.
- `sdks/python/src/qdash/sdk/calibration.py`: the definitions `Chip` takes, re-exported.
- `sdks/python/src/qdash/sdk/dashboard.py`: `Script`, `Dashboard`, `ScriptMetric`, `MetricScriptError`.
- `sdks/python/src/qdash/sdk/_dashboards.py`: `Scripts`, `SavedScript`, `Dashboards`, `SavedDashboard`.
- `sdks/python/hatch_build.py`: the `qdash-client` pin.
- `clients/python/src/qdash/client/services/client.py`: the pipeline, flow, metric script and dashboard route methods and `with_project`.
- `src/qdash/api/app/factory.py`: `OPENAPI_COMPONENT_MODELS`, which also publishes `MetricScriptPanelConfig`.
