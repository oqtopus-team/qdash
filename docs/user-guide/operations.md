# Operations

Use these commands to start, inspect, restart, and stop a Docker Compose deployment of QDash, and
to narrow down common failures.

Run all commands from the QDash repository root. The examples use the default ports from the
example `.env` files; use the values in your `.env` if you changed them.

## Start QDash

Start the enabled Docker Compose services:

```bash
docker compose up -d --build
```

If Go Task is installed, `task deploy-local` runs this command and also pulls the optional
Agent knowledge repository configured by `KNOWLEDGE_REPO_URL`.

The `agent-runtime`, `agent-exec` and `metric-runner` services start by default. Compose
generates and preserves internal authentication in the `agent-runtime-auth` volume. For a remote
deployment, follow [Enable Remote Access](./setup.md#enable-remote-access).

Host-side API and UI processes are a development workflow. Use
[Development Environment Setup](../developer-guide/setup.md) instead of the commands on this page.

## Check Service Health

List containers and their current state:

```bash
docker compose ps
```

After the containers start, check the browser-facing services:

- QDash UI: <http://localhost:5714/login>
- API documentation: <http://localhost:5714/api/docs>
- Prefect: <http://localhost:5714/prefect/dashboard>

## Inspect Logs

Follow a service log with `docker compose logs -f <service>`. Common service names are:

```bash
docker compose logs -f caddy
docker compose logs -f api
docker compose logs -f ui
docker compose logs -f deployment-service
docker compose logs -f user-flow-worker
docker compose logs -f prefect-server
docker compose logs -f agent-runtime
```

Press Ctrl+C to stop following a log; the service continues to run. Omit `-f` to print the current
log and return to the shell.

The API also writes a rotating file to its Docker log volume. Host-side API runs write under
`${XDG_STATE_HOME:-$HOME/.local/state}/qdash/logs`.

## Restart a Service

Restart one service after a transient failure or a configuration change that does not require a
new image:

```bash
docker compose restart api
```

Replace `api` with another service name from `docker compose ps`. If source, dependencies, or UI
build settings changed, recreate the service from a new image instead:

```bash
docker compose up -d --build api
```

`task restart-api` is the Go Task shortcut for restarting the API container.

## Upgrade Calibration Session Support

Calibration session support adds collections and indexes without rewriting existing calibration
history. Keep the existing database and configuration volumes when upgrading.

1. Stop accepting new calibration requests, including requests from external clients and
   scheduled workflows. Let running work finish before replacing services.
2. Confirm that the API and workflow worker use the same MongoDB host, port, and database.
   The execution repository now honors `MONGO_HOST` and, outside the `mongo` Docker hostname,
   `MONGO_PORT`, matching the other database connections.
3. Replace all API instances with the new release while requests remain stopped. Do not route
   requests across old and new API versions: an older API can ignore session association and
   retry fields and start an unrecorded run. Replace the UI, agent runtime, and workers with
   the matching release before reopening access.
4. Check startup logs for database or index errors and verify the service health. Existing
   executions must remain visible, and **Execution → Calibration sessions** must open.
5. Resume access, then update independently installed pi-qdash clients and SDKs. A client
   preflight does not make a mixed API deployment safe.

Releases that add the calibration session audit add the `calibration_decisions` collection and
two optional fields on recorded pipeline runs. Existing runs keep working and show their
missing request details as not recorded; nothing is backfilled.

Before rolling back, stop new requests and running agent conversations while the new API is
still available. Wait for in-flight measurements, parameter updates, and pipeline runs to
settle. Resolve every pending agent-session admission and every unknown pipeline outcome;
closing a calibration session does not cancel a pipeline already accepted for launch. If an
outcome cannot be established, keep the new API and investigate rather than rolling back.
An older API does not enforce the new admission checks. Keep requests stopped until all API,
runtime, UI, and worker instances use the selected release. Retain the added collections and
indexes; deleting them does not make an unresolved run safe to retry.

Releases that record every run in a calibration session add fields to the same collections and
an index on executions; existing records keep their meaning and are not moved into a session.
Upgrade the API and the workflow worker together: the worker records scheduled runs itself, and
an older API ignores the session and retry fields of a workflow or task launch. Rolling back
follows the steps above; sessions and runs recorded meanwhile stay in the database and remain
readable after a later upgrade.

The [admission and dispatch records](../developer-guide/agent/calibration-sessions.md#deployment-compatibility)
explain which states must be resolved before rollback.

## Open a Database Shell

MongoDB and PostgreSQL open no host port, so run their clients inside the containers with the
credentials from `.env`:

```bash
docker compose exec mongo sh -c 'mongosh --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin'
docker compose exec postgres sh -c 'psql --username "$POSTGRES_USER" "$POSTGRES_DB"'
```

## Stop QDash

Stop and remove the Compose containers and network:

```bash
docker compose down
```

This command preserves named volumes and bind-mounted data. Do not add `--volumes` unless you
intend to delete persistent service state.

The named volumes hold service logs, the AI runtime's internal authentication and workspace, and
saved AI conversations. The databases and calibration data live in the directories that `.env`
sets.
Deleting the `agent-runtime-state` volume removes AI chat transcripts and unfinished AI work; the
chat session list shown in QDash is kept in MongoDB and is unaffected.

## Resolve Common Failures

Start with [Check Service Health](#check-service-health), then match the symptom below.

### A Page Shows No Data

An empty page is not always a failure. Check, in order:

1. The active project and chip. Data belongs to one project, and a new project has no chips or
   runs until someone creates them; see
   [Active Project](./projects-and-data-sharing.md#active-project).
2. The page's scope. A time range, cool-down, status, or other filter can exclude every record.
3. The API. Open <http://localhost:5714/api/docs>. If it does not load, or the page shows a
   request error, read `docker compose logs caddy` and `docker compose logs api`. The `caddy`
   service forwards `/api` to the API container.

### A Workflow Run Reports a Missing Work Pool

Restart `deployment-service` and `user-flow-worker`. Both create the `user-flows-pool` work pool
when it is missing:

```bash
docker compose restart deployment-service user-flow-worker
```

### Task Figures Do Not Render

Confirm that `CALIB_DATA_PATH` in `.env` names the host directory that holds calibration figures
and raw data. Compose mounts that directory into the API and the workflow worker. After changing
it, recreate the services with `docker compose up -d`; figures written earlier stay in the
previous directory.

### Configuration Pages Report a Missing Path

Confirm that `CONFIG_PATH` in `.env` names the Qubex configuration tree on the host, as
[Qubex backend](./setup/qubex-backend.md#place-the-qubex-configuration) describes. Compose mounts
it into the API and the workflow worker; recreate them with `docker compose up -d` after changing
it.
