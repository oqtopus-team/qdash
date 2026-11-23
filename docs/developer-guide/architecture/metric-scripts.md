# Metric Scripts Architecture

Metric scripts run Python in the isolated `metric-runner` container. The API keeps authorization
and database access; a scoped broker supplies every value the script reads.

## Responsibility boundary

| Part | Responsibility |
| --- | --- |
| `MetricScriptService` | Permissions, revision, period, topology, and HTTP errors |
| API executor and broker | Send jobs and serve scoped data requests |
| Metric runner | Admission, per-job uid, supervision, and cleanup |
| Python worker | Validate/register metrics and compute results |

[Dashboards](./dashboards.md) covers revision pins and sharing.
[Metric Scripts](../../user-guide/metric-scripts.md) covers authoring.

## Evaluation flow

Validation executes the module in catalog mode without data access. Evaluation loads it again,
resolves parameters, and calls a scalar metric for each eligible topology target. `MissingData`
produces a missing cell; a target's error remains a cell error. Results are computed on demand,
not stored with the dashboard.

### Series results

Series metrics evaluate only selected targets. Timestamps must increase and remain inside the
period; values, counts, and statuses must agree. The worker does not sort or interpolate invalid
points. Bounds are 16 targets, 1,024 points per target, 8,192 points total, 6 MiB result JSON,
and a 400-day period. A bound failure is explicit rather than silently truncating the chart.

### Source formatting

`src/qdash/api/lib/python_format.py` runs bounded `ruff format --isolated` without executing source.
Formatting and saving are distinct from worker validation. Keep formatter arguments server-owned.

## Runner protocol

The API and runner exchange versioned newline-delimited JSON over a Unix socket. The runner
relays worker data requests back to the API; it receives no credentials or database connection.
`agent-runtime/metric-runner/protocol.ts` and the worker module document the wire formats.

## Data broker

Broker queries remain bound to the caller's project, chip, period, and allowed metric catalog.
Deadlines and concurrency caps limit database work. A query can finish after its worker stops,
so the broker retains its slot until the query actually returns.

## Isolation and threat model

Editors may validate or evaluate drafts. Viewers may evaluate only saved, validated revisions.
Each job runs with its own uid, a scrubbed environment, no network, and bounded process, memory,
time, and output use. Cleanup kills job processes and removes files before reusing a slot.

The import allowlist is a guardrail, not the sandbox. Container resources are shared across jobs;
there is no per-job cgroup. Keep the runner separate from the Agent workspace and API credentials.

## Local mode

`METRIC_RUNNER_MODE=local` runs as the API's user with its filesystem and network access. It is
for trusted development only; on macOS it has no address-space memory cap. Socket mode never
falls back to local execution: an unavailable runner returns 503.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `METRIC_RUNNER_MODE` | `socket` | Isolation mode |
| `METRIC_SCRIPT_TIMEOUT_SECONDS` | `60` | Requested job duration |
| `METRIC_SCRIPT_MEMORY_MB` | `1024` | Additional worker address space |
| `METRIC_BROKER_CONCURRENCY` | `4` | Data calls per API process |
| `METRIC_RUNNER_CONCURRENCY` | `2` | Jobs across API processes |
| `METRIC_RUNNER_QUEUE_LIMIT` | `16` | Waiting jobs |
| `METRIC_RUNNER_QUEUE_WAIT_SECONDS` | `5` | Maximum admission wait |
| `METRIC_RUNNER_MAX_TIMEOUT_SECONDS` | `300` | Runner duration cap |
| `METRIC_RUNNER_MAX_MEMORY_MB` | `1024` | Runner memory-request cap |
| `METRIC_RUNNER_MEMORY_LIMIT` | `3g` | Container memory shared by all jobs |

An overloaded queue returns 429. Runtime validation/evaluation failures carry diagnostics; do not
retry them as transport failures. Size the container for all concurrent jobs, Python baseline,
supervisor, and tmpfs together; increasing per-job memory alone can exhaust the container.

## Extending

Add broker operations with explicit scope and caps, plus a worker SDK accessor. Allowed imports
must be installed in both runner and local-test environments. New templates must validate and run
against fixture data. Keep socket and local protocols compatible.

## Tests

Run `uv run pytest tests/qdash/api/metric_runtime` and `task ci-agent-runtime` for runner changes.
Cover scope, timeout, resource cleanup, per-cell failures, series bounds, and malformed messages.

## Implementation Files

- `src/qdash/api/metric_runtime/executor.py`: API-side execution and limits.
- `src/qdash/api/metric_runtime/broker.py`: scoped data access.
- `src/qdash/api/metric_runtime/worker.py`: catalog and computation.
- `src/qdash/api/metric_runtime/sdk.py`: script author API.
- `agent-runtime/metric-runner/runner.ts`: isolated job supervision.
