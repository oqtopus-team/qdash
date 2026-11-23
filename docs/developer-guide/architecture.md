# Architecture

QDash separates the web UI, API, and calibration worker so each owns one part of a run.

<Diagram name="platform-architecture" caption="QDash services and their connections." />

## Components

| Component | Owns | Code |
| --- | --- | --- |
| [UI](./ui/architecture.md) | Pages, interactions, and client state | `ui/` |
| [API](./api/structure.md) | Authentication, project access, persistence, and dispatch | `src/qdash/api/` |
| [Workflow](./workflow/engine-architecture.md) | Task execution, hardware access, and calibration updates | `src/qdash/workflow/` |
| [Agent](./agent/architecture.md) | Chat and AI tools | `agent-runtime/`, `packages/` |

MongoDB stores application records. Prefect orchestrates runs and uses PostgreSQL.
API contract changes require `task generate` to update OpenAPI and the generated clients.

## Calibration Flow

1. The API saves a workflow and registers its Prefect deployment.
2. A run request reserves hardware, creates an execution ID, and starts a Prefect run.
   A conflicting reservation returns HTTP 409.
3. The worker executes the tasks and saves results in the selected project and chip.
4. Accepted outputs become inputs to later tasks. Completion or cancellation releases the reservation.

<Diagram name="calibration-flow" caption="Dispatch, task execution, and completion of a calibration." />

See the [workflow engine](./workflow/engine-architecture.md) for lifecycle rules and
[calibration data](./workflow/calibration-data-lifecycle.md) for what gets saved.

## Browser Entry Point

Only Caddy publishes a host port in `compose.yaml`, on `UI_PORT`.
`config/caddy/Caddyfile` routes requests as follows:

| Browser path | Destination |
| --- | --- |
| `/api/*` | QDash API |
| `/prefect/api/*` | Prefect API, after a QDash access check |
| `/prefect/*` | Prefect UI, after a QDash access check |
| Other paths | Next.js UI |

Internal services use Compose service names. Separate production stacks need different `ENV`
and `UI_PORT` values.

### Development Routing

`task dev-local` adds `compose.dev-local.yaml`: Caddy routes to hot-reload API and UI processes.
On macOS they listen on loopback; on Linux they listen on `0.0.0.0` so Docker can reach them.
Use `QDASH_DEV_BIND` to restrict a Linux listener. In a DevContainer, the stack must share its `ENV`.
See [Setup](./setup.md#run-the-development-stack) for commands and ports.

### Proxy Trust and Prefect Access

Caddy replaces forwarded scheme headers. The API trusts callers reaching its private port;
a Linux development listener can extend that trust to the local network.
Prefect requires QDash sign-in. Administrators can write; other users get only the read operations
allowed by `src/qdash/api/lib/prefect_access.py`. Keep Prefect CSRF protection enabled.

Caddy also forwards chat streams and Next.js HMR. Preserve incremental delivery and cancellation
when changing proxy configuration.

### Proxy Tests

Run `uv run pytest tests/infra tests/qdash/api/lib/test_prefect_access.py tests/qdash/api/routers/test_auth_prefect_access.py` from the repository root.
Proxy integration tests need Caddy on `PATH` or `CADDY_BIN`; otherwise they skip.
