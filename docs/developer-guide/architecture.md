---
layout: doc
---

# Architecture

QDash consists of three major components.

- UI
  - Next.js frontend for workflow operation, monitoring, and analysis
- API
  - FastAPI backend that handles user requests, authentication, project access, and database access
- Workflow
  - Prefect-based calibration workflow runtime, deployment service, and user flow worker

<Diagram name="platform-architecture" caption="QDash runtime services and the requests between them." />

## Components

### QDash UI

The UI is the frontend for users, developed with Next.js and React. It provides pages for
dashboarding, chip/task inspection, workflow editing and execution, metrics, provenance, issue
tracking, file management, and Copilot-assisted analysis.

The UI client and standalone TypeScript client are generated with Orval from the API's OpenAPI
schema. API contract changes therefore require client regeneration with `task generate`.
[UI Architecture](./ui/architecture.md) maps the routes, component boundaries, and state flow.

![qdash-ui](/images/qdash-ui.png)

### QDash API

The API receives user requests, enforces authentication and project access, communicates with
MongoDB and Prefect, and exposes the OpenAPI schema used to generate the UI and standalone TypeScript clients.
[API Code Structure](./api/structure.md) maps routers, schemas, services, and dependencies.

![server-example](/images/server-example.png)

### QDash Workflow

The workflow component manages qubit calibration workflows. Prefect is the workflow engine, while
QDash stores user flow files, registers Prefect deployments through the deployment service, and
executes user flows with the user flow worker.

Calibration task implementations call the laboratory libraries they need, while QDash supplies
execution context, parameter resolution, persistence, scheduling, and status tracking.
[Workflow Engine Architecture](./workflow/engine-architecture.md) maps the runtime responsibilities
and extension points.

![workflow-example](/images/qcflow-example.png)

### Calibration Flow

Calibration follows this flow.

1. The user selects a project, chip, targets, and workflow or task in the UI or client.
2. When the user saves a flow, the API asks the deployment service to register its Prefect deployment. Running the flow reuses that deployment.
3. On execution, the API claims the execution lock for the hardware the run needs and mints the execution ID in the same step. It returns 409 if another run holds the lock. The execution ID links the run, task results, logs, and artifacts.
4. The API creates a Prefect flow run from the deployment and records a `scheduled` execution. The user flow worker picks up the run and adopts that execution.
5. The worker runs each task through preprocess, run, postprocess, validation, and save. Task implementations can call experimental libraries such as qubex.
6. Task results and accepted calibration changes are stored in their project and chip context.
7. Parameter resolution can use the current accepted state as input to later tasks.
8. If a user cancels a running execution, the API sends a cancel request to Prefect, which terminates the worker process via SIGTERM. The `on_cancellation` hook then updates the execution and task statuses to `cancelled` and releases the execution lock.

<Diagram name="calibration-flow" caption="How a calibration run is dispatched, executed task by task, and closed or cancelled." />

The [Workflow Engine Architecture](./workflow/engine-architecture.md) describes the
runtime components in detail. [Projects and Data Sharing](../user-guide/projects-and-data-sharing.md)
explains the user-visible boundary for project-scoped state and artifacts.

## Browser Entry Point

The `caddy` service is the only service of `compose.yaml` that publishes a host port. It listens
on `UI_PORT` and routes by path with `config/caddy/Caddyfile`:

| Path | Upstream | Upstream path |
| --- | --- | --- |
| `/api`, `/api/*` | `api` (`QDASH_API_UPSTREAM`) | Unchanged; the API app runs with `root_path="/api"`, which removes the prefix for routing and adds it to URLs the API builds |
| `/prefect/api`, `/prefect/api/*` | `prefect-server` after the access check | `/api/*`, Prefect's API path |
| `/prefect`, `/prefect/*` | `prefect-server` after the access check | Unchanged; Prefect serves its UI there |
| Everything else | `ui` (`QDASH_UI_UPSTREAM`) | Unchanged |

Prefect keeps its API at `/api`, so the API, the deployment service, and the worker use
`http://prefect-server:4200/api` as before. Only the browser-facing settings move:
`PREFECT_SERVER_UI_SERVE_BASE=/prefect` and `PREFECT_SERVER_UI_API_URL=/prefect/api`.

The other services reach each other by service name on the Compose project's `custom_net` and
publish no host port, not even on loopback. Two stacks on one host therefore conflict only on
`UI_PORT` and the Compose project name, which comes from `ENV`; the internal port settings can
stay identical. Deployment tasks and a plain `docker compose up -d` load `compose.yaml` alone.

`compose.yaml` sets `QDASH_API_UPSTREAM` to `api:${API_PORT}` and `QDASH_UI_UPSTREAM` to
`ui:${UI_PORT}`. Under `task dev-local`, the same `caddy` service and Caddyfile serve
development: `compose.dev-local.yaml` points both upstreams at
`${QDASH_DEV_HOST}:${API_PORT}` and `${QDASH_DEV_HOST}:${UI_DEV_PORT}`, where the API runs
under `uvicorn --reload` and Next.js under `next dev`. The overlay replaces Caddy's dependency
on `api` and `ui` with `!override`, so the production images are neither built nor started.
`QDASH_DEV_HOST` selects where those processes run:

| Where `task dev-local` runs | `QDASH_DEV_HOST` | Listen address of the API and Next.js |
| --- | --- | --- |
| macOS host (Docker Desktop, OrbStack) | `host.docker.internal` (default) | `127.0.0.1`; Docker forwards `host.docker.internal` to host loopback |
| Linux host | `host.docker.internal` (default), mapped to the Docker host gateway by `extra_hosts: host-gateway` | `0.0.0.0`, because the gateway cannot reach loopback; other machines on the network can reach both ports |
| DevContainer | `devcontainer`, set by `compose.devcontainer.yaml` | `0.0.0.0` inside the container, reachable only on the project's `custom_net` |

`QDASH_DEV_BIND` overrides the listen address, for example to the Docker bridge gateway
(`172.17.0.1` by default) on a Linux host. A firewall that drops container traffic to the host,
such as ufw's default policy, makes Caddy answer 502. In the DevContainer, Caddy resolves
`devcontainer` only when the DevContainer and the stack share the Compose project, that is, the
same `ENV`.

The overlay also points the Pi Agent Runtime's `QDASH_BASE_URL` at the development API and
publishes MongoDB, Prefect, the deployment service, and the runtime on `127.0.0.1` for a host
API. The browser still reaches only Caddy; the runtime port accepts only the runtime credential,
which `task dev-api-local` reads from the running container unless `AGENT_RUNTIME_TOKEN` is set.
In the DevContainer, the API uses the service names instead.

Caddy trusts no client's `X-Forwarded-*` headers. It sends every upstream its own
`X-Forwarded-Proto`: `https` when the request's host is the host of an `https://` `CLIENT_URL`,
such as the Cloudflare Tunnel hostname, and `http` for any other host, such as `localhost`.
TLS terminates in front of Caddy, so Caddy itself only receives HTTP. The API runs gunicorn with
`--forwarded-allow-ips=*`, so redirects such as `/api/auth/me/` to `/api/auth/me` keep the
browser's scheme; its default trust covers only loopback, not Caddy's address on `custom_net`.
This trusts every caller that reaches the API port, which is not published on the host: Caddy
and other containers on `custom_net`. A forwarded header only changes URLs in the response to
that caller and grants no access.
`task dev-api-local` passes the same option to uvicorn; on a Linux host its `0.0.0.0` listener
extends that trust to the local network.

Before Caddy forwards a Prefect request, it calls `GET /auth/prefect-access` on the API with the
`access_token` cookie as the bearer token and the original method, URI, and `Upgrade` header in
`X-Forwarded-*` headers. The route is excluded from the OpenAPI schema. A 2xx response lets the
request continue; any other status is returned to the browser, and a signed-out page navigation
is redirected to `/login`. A system administrator may make any Prefect request. Other users may
make read requests: `GET` and `HEAD` without `include_secrets`, the allowlisted `POST` queries in
`src/qdash/api/lib/prefect_access.py`, and the `events/out` and `logs/out` websockets. The
classifier matches the raw URI, so encoded or dot-segment variants of a query path are denied.
Prefect's CSRF protection (`PREFECT_SERVER_API_CSRF_PROTECTION_ENABLED`) stays on because the
browser session reaches Prefect with a cookie; Prefect's Python client fetches CSRF tokens
itself.

Next.js has no rewrites or route handlers under `/api`. The Prefect access check and the
Copilot chat stream therefore pass through Caddy in development as in production. Caddy flushes
each `text/event-stream` chunk as it arrives and closes the API's connection when the browser
closes its own, so the API sees a stopped chat as a disconnect. It also proxies the Next.js HMR websocket at
`/_next/hmr` with the browser's `Host` header. Next.js accepts it for `localhost`; list any
other hostname in `NEXT_ALLOWED_DEV_ORIGINS`.

The `ui` service sets `pull_policy: build`, so a plain `docker compose up -d` rebuilds the UI
image from the current checkout instead of reusing an image built from older code.

`tests/infra/test_compose_ingress.py` renders `compose.yaml` with an unchanged older `.env` and
checks the published ports and Prefect settings, and renders `compose.dev-local.yaml` for the
development upstreams and dependencies. `tests/infra/test_caddy_proxy.py` runs the
Caddyfile against mock upstreams and against the QDash API served by the `compose.yaml` gunicorn
command, including incremental SSE delivery, cancellation, and the HMR websocket. It also runs
the Caddyfile in front of the Prefect UI of the installed `prefect` package: opening
`/prefect/dashboard` or a flow run page returns the UI and its assets, and Prefect API errors
reach the browser unchanged. Prefect returns its UI for these paths only to requests that accept
`text/html`, as browser navigations do. The tests skip
unless `CADDY_BIN` or `caddy` on `PATH` provides Caddy. The access rules are tested in `tests/qdash/api/lib/test_prefect_access.py` and
`tests/qdash/api/routers/test_auth_prefect_access.py`.
