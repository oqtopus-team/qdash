# Python SDK

`qdash.sdk` builds calibration, metric-script, and dashboard requests on top of `qdash.client`.
The client owns transport and authentication; the API owns permissions and hardware validation.

## Define, check, run

| Operation | Effect |
| --- | --- |
| Construct a `Pipeline`, target, step, or `Chip` | Local definition only |
| `chip.validate_calibration(...)` | Server validation, no execution |
| `chip.calibrate(...)` | Dispatch a calibration pipeline |
| `qdash.workflows.get(...)` | Read a registered workflow |
| `workflow.run(...)` | Dispatch its saved deployment |
| `run.wait()` | Poll the whole run to a terminal state |

No phase implicitly starts the next. The SDK never imports or executes workflow source locally.
Python dispatch requires an explicit project. Validation does not reserve hardware; the server
validates again at execution.

## Session and client ownership

`QDash.from_env()` and `from_profile()` own their client; `close()` or a `with` block closes it.
`QDash(client)` borrows the caller's client and never closes it. Chips share the session's
connection and project. The SDK keeps no separate run registry or catalog cache.

## Following a run

Run handles wait for pipeline-wide status, retry an initial execution 404, return failed/cancelled
outcomes, and raise `TimeoutError` on timeout. A timeout does not prove the operation stopped.

Pass `calibration_session_id` and `idempotency_key` to `qdash.pipelines.execute()` or
`qdash.workflows.run()` to associate and safely retry a launch.
`decision_id` requires a session. If a response fails to echo requested association fields,
reconcile the possible launch rather than retrying with a new key. See
[Calibration Sessions](../agent/calibration-sessions.md).

## Metric scripts and dashboards

`Script` and `Dashboard` are authoring objects; save them through the session. Script source is
text written for the worker's `qdash_metrics` API, not code imported by the SDK. A saved script
handle binds its revision, and dashboard panels pin that revision. Updates send expected revisions
or versions so concurrent edits fail explicitly.

## Shared models

Pipeline definitions derive from server models through OpenAPI. To extend them, change
`src/qdash/datamodel/calibration_pipeline.py`, run `task generate`, then update SDK helpers and
tests. Never hand-edit generated clients or duplicate server-dependent checks locally.

## Packaging and release

`qdash-sdk` depends on the matching `qdash-client`. They share the implicit `qdash` namespace;
do not add `qdash/__init__.py`. [Pi Packages](../agent/packages.md#distribution) describes the
common release pipeline. Usage examples live in the [Python client reference](../../reference/clients/python.md).

## Implementation Files

| File | Responsibility |
| --- | --- |
| `sdks/python/src/qdash/sdk/_session.py` | Session and client ownership |
| `sdks/python/src/qdash/sdk/_calibration.py` | Chip front door |
| `sdks/python/src/qdash/sdk/_pipelines.py` | Pipeline dispatch and handles |
| `sdks/python/src/qdash/sdk/_workflows.py` | Registered workflows |

Run `task test-sdk` from the repository root after changes; tests live in `sdks/python/tests/`. Cover serialization, project scope,
no implicit dispatch, whole-run polling, uncertain responses, and revision conflicts.
