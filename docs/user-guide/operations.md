# Operations

Use these commands to start, inspect, restart, and stop a local or lab QDash deployment.

Run all commands from the QDash repository root. The examples use the default ports from the
example `.env` files; use the values in your `.env` if you changed them.

## Start QDash

Start the enabled Docker Compose services:

```bash
docker compose up -d --build
```

If Go Task is installed, `task deploy-local` runs this command and also pulls the optional
Copilot knowledge repository configured by `KNOWLEDGE_REPO_URL`.

The `agent-runtime` and `agent-exec` services start by default. Compose generates and preserves
internal authentication in the `agent-runtime-auth` volume. For a remote deployment, follow
[Enable Remote Access](./setup.md#enable-remote-access).

Host-side API and UI processes are a development workflow. Use
[Development Environment Setup](../developer-guide/setup.md) instead of the commands on this page.

## Check Service Health

List containers and their current state:

```bash
docker compose ps
```

After the containers start, check the browser-facing services:

- QDash UI: <http://localhost:5714/login>
- API documentation: <http://localhost:5715/docs>
- Prefect: <http://localhost:4200>

## Inspect Logs

Follow a service log with `docker compose logs -f <service>`. Common service names are:

```bash
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

Pi stores per-user durable conversation state in the `agent-runtime-state` Docker volume. Normal
container rebuilds preserve it. Deleting that volume removes Pi transcripts and unfinished work;
the user-facing session list in MongoDB is unaffected.

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

## Stop QDash

Stop and remove the Compose containers and network:

```bash
docker compose down
```

This command preserves named volumes and bind-mounted data. Do not add `--volumes` unless you
intend to delete persistent service state.

## Resolve Common Failures

If the UI cannot reach the API, check `INTERNAL_API_URL` and whether the API is listening on
`API_PORT`.

If workflow execution fails with a missing work pool, restart `deployment-service` and
`user-flow-worker`; the deployment service creates the `user-flows-pool` when registering flows.

If task figures do not render, confirm `CALIB_DATA_PATH` points at the directory mounted to
`/app/calib_data` in Docker.

If Qubex config or task file pages return missing-path errors, confirm `CONFIG_PATH` points
to the Qubex backend configuration tree and `CALIB_TASKS_PATH` points to the calibration
task directory in `.env`.
