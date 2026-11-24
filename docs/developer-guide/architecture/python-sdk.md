# Python SDK

`qdash.sdk` contains a Fern-generated API client and handwritten calibration, workflow, and
dashboard helpers. It has no dependency on `qdash-client`; that package remains available to
existing applications. The server owns permissions and hardware validation.

## Define, check, run

Use `qdash.sdk.CalibrationSession` to create or open a named calibration objective and run
trials in it. `qdash.calibration` supplies the same targets, built-in steps, task calls, and
sweeps that workflows use. Definitions do not import the worker or contact the server.

| Operation | Effect |
| --- | --- |
| Construct targets, steps, or task calls | Local definition only |
| `CalibrationSession.create(client, chip_id=..., name=...)` | Create an objective record; no hardware reservation |
| `CalibrationSession.open(client, session_id=...)` | Read the existing objective, including closed ones |
| `session.validate(targets, steps)` | Server validation, no execution |
| `session.submit(targets, steps)` | Dispatch into the objective and return `CalibrationLaunch` |
| `session.run(targets, steps)` | Dispatch, wait, and return `CalibrationResult` on completion |
| `session.close()` | Request closure; no cancellation or HTTP-client cleanup |

`run()` and `CalibrationLaunch.wait()` raise `CalibrationRunError` for unsuccessful terminal
runs and `TimeoutError` without cancellation on timeout. `CalibrationLaunch.get()` returns a
snapshot, including nonterminal states. The handle follows the recorded session/run IDs, so
failure before the first execution is observable. Explicit objectives stay open for more trials.
See [usage and recovery](../../reference/clients/python.md#run-a-calibration).

`qdash.workflow.CalibrationSession` executes those same definitions in the current flow run;
several calls share the enclosing run identity. Its `run()` returns the same `CalibrationResult`
type, with typed runtime step results; SDK step details are server progress records. Completion
means the steps finished, not that every target passed calibration. Workflow execution errors
propagate to Prefect; SDK failures include the remote result in `CalibrationRunError.result`.
Workflow `validate()` checks structure and dependency order locally; SDK `validate()` also
performs the server's chip/data preflight. Neither reserves hardware.

The existing `chip.calibrate(...)`, `qdash.pipelines.execute(...)`, and workflow helpers retain
their asynchronous handles and failure-result behavior. `Pipeline` remains available from
`qdash.sdk.pipeline` for stored specs. The SDK never executes saved workflow source locally.
Python dispatch requires an explicit project; the server validates again before executing.

### Definitions and Step Results

`qdash.calibration.ExecutionStep` is the common base of built-in step definitions;
`CalibrationStepDefinition` is an alias. Concrete names such as `CustomOneQubit` and
`FilterByStatus` stay unchanged. Every reached step records an Execution, including transforms
that perform no measurements. The SDK keys step progress by its plan occurrence key so repeated
filters remain distinct. Transform progress carries the copied outcome in `transform`.
Workflow results retain typed calibration steps in `steps` and transform snapshots under
`details["transforms"]`. Unrecorded historical transforms are not inferred or backfilled.

## Client ownership

Create one `QDash` client and reuse it across operations or notebook cells.
`QDash(config)`, `from_env()`, and `from_profile()` own their HTTP connection; call `close()`
when the client is no longer needed. A `with` block is an optional way to close it on exit. `QDash(config, http_client=...)` borrows an `httpx.Client` and never
closes it. The supplied client's TLS and proxy settings apply. `with_project()` creates a
client on the same connection without taking ownership. Close the owning client last.

`qdash.api` exposes generated resources with the client's authentication and project header.
Generated calls disable retries by default. Helper reads may retry transient failures according
to `QDashConfig.read_attempts`; helper writes send once, including on 409, 5xx, and timeouts.
Helpers translate HTTP errors to SDK errors; direct generated calls retain generated exceptions
and httpx errors. Password authentication caches a token without refreshing on 401; create a
new client after expiry, or use API tokens. Read helpers retry connection and remote protocol
errors, but not read timeouts. Writes retain a single attempt. A client snapshots its
configuration; `config` returns a copy, and `with_project()` explicitly changes scope.

Profiles use `config.toml` with `[profiles.<name>]` tables. Explicit profile selection takes
precedence over `default_profile`, then `"default"`. The SDK reads deprecated INI only when
the default TOML file is absent or the caller explicitly supplies an INI path; it emits
`QDashConfigDeprecationWarning`. TOML errors never trigger fallback. `api_token_env` resolves
only the selected profile's token. See the [migration procedure](../../reference/clients/python.md#migrate-an-ini-profile).

## Following a run

`qdash.run(execution_id)` creates a handle for an existing execution without dispatching work.
`RunResult.succeeded` reports successful completion; `RunResult.done` reports any terminal
status. Both use the same whole-run status as `RunResult.status` and send no request.
Run handles wait for pipeline-wide status, retry an initial execution 404, return failed/cancelled
outcomes, and raise `TimeoutError` on timeout. A timeout does not prove the operation stopped.

Registered `WorkflowRun` handles instead use the session and run IDs to read
`GET /calibration-sessions/{session_id}/runs/{run_id}`. This endpoint observes Prefect on
request without closing the session or trusting cached terminal state. It retrieves the run
directly, beyond the session detail's recent-run limit. Unknown or unavailable observations
do not end SDK polling. Execution statuses remain local to each execution. `WorkflowRunResult` is independent of
`RunResult`; its optional `detail` does not gate terminal status, since a workflow can end
before creating an execution.

Recorded-run reads verify both session and run IDs in the response. `WorkflowRun.cancel()`
uses the launch response's Prefect flow UUID with the existing cancellation endpoint. It
sends one POST without retries and leaves completion polling to `wait()`; it never selects
an execution or closes the calibration session.

Pass `calibration_session_id` and `idempotency_key` to `qdash.pipelines.execute()` or
`qdash.workflows.run()` to associate and safely retry a launch.
`decision_id` requires a session. If a response fails to echo requested association fields,
reconcile the possible launch rather than retrying with a new key. See
[Calibration Sessions](../agent/calibration-sessions.md).

## Investigation lists

`qdash.executions` and `qdash.task_results` wrap the server's paginated summary endpoints.
Pages retain filters for explicit `next_page()` requests. Iteration and conversion never
fetch more data. `to_records()` returns flat columns; `to_dataframe()` imports pandas lazily.
Display libraries are separate consumers. Offset pagination is not a stable snapshot while
new records arrive. See [list filters](../../reference/clients/python.md#list-executions-and-task-results).

## Execution inspection and single-task runs

`qdash.execution(id).get()` reads one execution. Its `ExecutionResult.status` is local to
that execution; `RunResult.status` remains the whole-run status. `run.executions()` reads
started steps in index order and deduplicates execution IDs. Task wrappers preserve parameter
metadata and invocation identity; `_parameters.py` exposes concise `Parameter` values and
read-only `Parameters` mappings with optional DataFrame conversion; `qdash.task_result(id)` reads the full persisted record.
Artifact handles fetch bytes only through explicit `read()`, `save()`, or `Figure.show()` calls,
using the configured client. Notebook display imports IPython lazily.

`qdash.tasks` reads the Workbench catalog and dispatches through `quick_run_task`.
`Tasks.load_parameters()` reads the catalog and current qubit/coupling values into an
editable `TaskParameters` snapshot, resolving declared roles, aliases, fallbacks, and defaults.
`to_call()` preserves sweep declarations and omits forbidden overrides; unknown resolution
rules remain unresolved for the worker. It never dispatches or claims full runtime validation.
`TaskCall.run` and `input` map to parameter overrides without expanding sweeps locally.
Single-task calls reject pipeline-only `call_id` and `on_failure`. An unset writeback policy
resolves to false here; pipeline inheritance is unchanged. `source_task_id` is provenance,
not a historical-state restore. Task and workflow launches share recorded-association checks.
See [the usage examples](../../reference/clients/python.md#run-a-task-from-the-workbench).

## Metric scripts and dashboards

`Script` and `Dashboard` are authoring objects; save them through the client. Script source is
text written for the worker's `qdash_metrics` API, not code imported by the SDK. A saved script
handle binds its revision, and dashboard panels pin that revision. Updates send expected revisions
or versions so concurrent edits fail with `QDashConflictError`.

## Device gateway exports

`qdash.device_topology.create()` computes a topology from the latest master calibration
note in the project; `device_id` labels the result, not a chip selector. JSON preserves API
field aliases. `plot()` fetches a PNG once; displaying the returned plot sends no request.
Both POST computations use a single attempt and do not change server state.

`qdash.qubex.download_config()` downloads the configured root using the relative path `.`
and optionally adds the latest calibration note. The archive and note are separate reads.
Extraction validates archive paths and file conflicts before writing. A new destination is
assembled beside its final path; existing destinations are updated one file at a time.
See [the export procedure](../../user-guide/device-gateway-export.md).

## Shared models

`qdash.calibration` lives in `sdks/python/src/qdash/calibration` and ships in `qdash-sdk`.
The server depends on that workspace package and imports the same definitions. The module
requires neither Prefect nor a database. Worker adapters in `service/definitions.py` convert
shared targets and steps into runtime executors. Runtime custom steps remain worker-only.
Docker Compose mounts the shared sources for API, deployment, and workflow services.

`docs/oas/openapi.json` remains the source for generated API resources and wire authoring
models. Fern generates `_generated/`; `types.py` exposes response types.
`_generated/_authoring.py` preserves request-schema constraints for the compatibility pipeline
API. Shared authoring definitions serialize to spec version 2; the server validates that wire
spec. Tests compare shared definitions against server validation and verify isolated SDK wheels.
Response models tolerate extra fields for compatibility with server additions.

To extend the API, update the server schemas and run `task generate`. For SDK-only generation,
run `task generate-python-sdk`. Both need Node.js (`npx`) and a running Docker daemon. The
CLI and generator versions are pinned in `sdks/python/fern/`; local generation uses the legacy
`generators.yml` format and needs no Fern login. Change generation settings there, never in the
output files. Keep generated imports under `qdash.sdk._generated`.

`scripts/generate_python_sdk.py` retains Python sources and excludes variable generation
metadata. `task check-python-sdk-generated` regenerates and compares the output; it also runs
in `ci-lint`. New endpoints become available through `qdash.api` without handwritten wrappers.
Add helpers only for QDash-specific composition or behavior.

## Packaging and release

`qdash-sdk` and `qdash-client` install independently and share the implicit `qdash` namespace;
do not add `qdash/__init__.py`. [Pi Packages](../agent/packages.md#distribution) describes the
common release pipeline. Usage examples live in the [Python client reference](../../reference/clients/python.md).

## Implementation Files

| File | Responsibility |
| --- | --- |
| `sdks/python/src/qdash/sdk/_session.py` | Client and connection ownership |
| `sdks/python/src/qdash/sdk/_calibration_session.py` | Objective lifecycle and recorded-run dispatch/wait |
| `sdks/python/src/qdash/calibration/` | Shared authoring definitions and results |
| `sdks/python/src/qdash/sdk/_config.py` | Environment and profile settings |
| `sdks/python/src/qdash/sdk/_http.py` | Authentication, HTTP configuration, error translation |
| `sdks/python/src/qdash/sdk/errors.py` | SDK exception types |
| `sdks/python/src/qdash/sdk/_runs.py` | Execution lookup and whole-run polling |
| `sdks/python/src/qdash/sdk/_device_topology.py` | Device topology computation and JSON/PNG exports |
| `sdks/python/src/qdash/sdk/_qubex.py` | Configuration archive and calibration note downloads |
| `sdks/python/src/qdash/sdk/_history.py` | Paginated investigation lists and tabular conversion |
| `sdks/python/src/qdash/sdk/_results.py` | Execution/task snapshots and artifact handles |
| `sdks/python/src/qdash/sdk/_tasks.py` | Task catalog and Workbench dispatch |
| `sdks/python/src/qdash/sdk/_chips.py` | Project chip metadata reads |
| `sdks/python/src/qdash/sdk/_calibration.py` | Chip front door |
| `sdks/python/src/qdash/sdk/_pipelines.py` | Pipeline dispatch and handles |
| `sdks/python/src/qdash/sdk/_workflows.py` | Registered workflows |

Run `task test-sdk` from the repository root after changes; tests live in `sdks/python/tests/`. Cover serialization, project scope,
no implicit dispatch, whole-run polling, uncertain responses, and revision conflicts.
