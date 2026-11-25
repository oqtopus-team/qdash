# Operations

Run these commands from the repository root to operate a Docker Compose deployment.

## Start QDash

```bash
docker compose up -d --build
```

`task deploy-local` also updates the configured knowledge repository. For host-side processes,
use [developer setup](../developer-guide/setup.md).

## Check Service Health

Run `docker compose ps`, then open QDash at <http://localhost:5714/login>, API docs at
<http://localhost:5714/api/docs>, or Prefect at <http://localhost:5714/prefect/dashboard>.
Use your configured host and port if different.

## Inspect Logs

```bash
docker compose logs -f api
```

Replace `api` with `caddy`, `ui`, `deployment-service`, `user-flow-worker`, `prefect-server`, or
`agent-runtime`. Ctrl+C stops following the log, not the service.

## Restart a Service

Use `docker compose restart api` for a transient failure. After `.env` changes, recreate with
`docker compose up -d api`; after source or dependency changes, add `--build`.

## Upgrade Calibration Session Support

1. Stop new requests, schedules, and external writers; let running work finish.
2. Confirm API and workers use the same MongoDB host, port, and database.
3. Replace all API instances, UI, runtime, and workers with the same release before reopening
   access. Mixed versions can ignore session or retry fields and start unrecorded work.
4. Check startup logs, existing executions, and **Execution → Calibration sessions**.
5. Resume access and update independently installed clients.

Keep existing volumes, collections, and indexes. Older executions remain readable without being
backfilled into sessions.

Before rollback, stop new requests and agent conversations while the new API is available.
Wait for measurements, commits, and pipeline runs to settle, then resolve pending admissions
and unknown launch outcomes. Closing a session does not cancel admitted work. If an outcome
cannot be established, keep the new API and investigate. Reopen access only after every service
uses the selected release. See [deployment compatibility](../developer-guide/agent/calibration-sessions.md#deployment-compatibility).

## Open a Database Shell

Databases expose no host port. Use their container credentials:

```bash
docker compose exec mongo sh -c 'mongosh --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin'
docker compose exec postgres sh -c 'psql --username "$POSTGRES_USER" "$POSTGRES_DB"'
```

## Stop QDash

```bash
docker compose down
```

This preserves data. Do not add `--volumes` unless deleting persistent service state is intended.
In particular, deleting `agent-runtime-state` loses conversations and unfinished AI work.

## Resolve Common Failures

### Investigate an Error ID

Some file and workflow errors display **Error ID** after the message.

1. Copy the message and ID, and record the operation and approximate time. If you do not operate
   the deployment, send these details to its operator.
2. As the operator, run `docker compose logs --since 30m api`, adjusting the time window as needed,
   and locate the exact ID. The matching entry includes the underlying error and traceback.
3. Resolve the cause, then check the file or workflow's saved state before retrying a write.

Not every error has an ID. For those errors, use the operation and time to locate the API logs.

### A Page Shows No Data

Check the active project, chip, time range, and filters. If requests fail, inspect `caddy` and
`api` logs.

### A Workflow Run Reports a Missing Work Pool

```bash
docker compose restart deployment-service user-flow-worker
```

Both services create the missing work pool.

### Task Figures Do Not Render

Check `CALIB_DATA_PATH` in `.env`, then recreate with `docker compose up -d`. Existing figures
remain in the old directory when the path changes.

### Configuration Pages Report a Missing Path

Check `CONFIG_PATH` against the [Qubex tree](./setup/qubex-backend.md#place-the-qubex-configuration),
then recreate with `docker compose up -d`.

### Files Are Missing from a Configuration ZIP

**Download as ZIP** skips symbolic links to directories and files outside the configuration
tree. Links to regular files inside the tree are included. If a required file is missing,
place a regular copy inside the configuration tree and download again. Check the API logs
for skipped links.
