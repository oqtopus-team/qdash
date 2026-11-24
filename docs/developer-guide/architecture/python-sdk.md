# Python SDK

`qdash.sdk` contains a Fern-generated API client and handwritten calibration, workflow, and
dashboard helpers. It has no dependency on `qdash-client`; that package remains available to
existing applications. The server owns permissions and hardware validation.

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

Create one `QDash` session and reuse it across operations or notebook cells.
`QDash(config)`, `from_env()`, and `from_profile()` own their HTTP connection; call `close()`
when the session is no longer needed. A `with` block is an optional way to close it on exit. `QDash(config, http_client=...)` borrows an `httpx.Client` and never
closes it. The supplied client's TLS and proxy settings apply. `with_project()` creates a
session on the same connection without taking ownership. Close the owning session last.

`qdash.api` exposes generated resources with the session's authentication and project header.
Generated calls disable retries by default. Helper reads may retry transient failures according
to `QDashConfig.read_attempts`; helper writes send once, including on 409, 5xx, and timeouts.
Helpers translate HTTP errors to SDK errors; direct generated calls retain generated exceptions
and httpx errors. Password authentication caches a token without refreshing on 401; create a
new session after expiry, or use API tokens. Read helpers retry connection and remote protocol
errors, but not read timeouts. Writes retain a single attempt. A session snapshots its
configuration; `config` returns a copy, and `with_project()` explicitly changes scope.

Profiles use `config.toml` with `[profiles.<name>]` tables. Explicit profile selection takes
precedence over `default_profile`, then `"default"`. The SDK reads deprecated INI only when
the default TOML file is absent or the caller explicitly supplies an INI path; it emits
`QDashConfigDeprecationWarning`. TOML errors never trigger fallback. `api_token_env` resolves
only the selected profile's token. See the [migration procedure](../../reference/clients/python.md#migrate-an-ini-profile).

## Following a run

`qdash.run(execution_id)` creates a handle for an existing execution without dispatching work.
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
or versions so concurrent edits fail with `QDashConflictError`.

## Shared models

`docs/oas/openapi.json` is the source for both generated API resources and authoring models.
Fern generates `_generated/`; `types.py` exposes response types. `_generated/_authoring.py`
is generated with datamodel-code-generator from the request schemas used by the helpers.
It preserves schema constraints that the pinned Fern generator omits, including pipeline
patterns, constants, and defaults. Unknown fields are rejected only where the schema closes
an object. Response models tolerate extra fields for compatibility with server additions.

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
| `sdks/python/src/qdash/sdk/_session.py` | Session and connection ownership |
| `sdks/python/src/qdash/sdk/_config.py` | Environment and profile settings |
| `sdks/python/src/qdash/sdk/_http.py` | Authentication, HTTP configuration, error translation |
| `sdks/python/src/qdash/sdk/errors.py` | SDK exception types |
| `sdks/python/src/qdash/sdk/_runs.py` | Execution lookup and whole-run polling |
| `sdks/python/src/qdash/sdk/_calibration.py` | Chip front door |
| `sdks/python/src/qdash/sdk/_pipelines.py` | Pipeline dispatch and handles |
| `sdks/python/src/qdash/sdk/_workflows.py` | Registered workflows |

Run `task test-sdk` from the repository root after changes; tests live in `sdks/python/tests/`. Cover serialization, project scope,
no implicit dispatch, whole-run polling, uncertain responses, and revision conflicts.
