QDash system updates let a system administrator deploy the latest stable source release without
giving the API process direct Git or Docker access.

## Architecture

The updater is a small host-side process that runs outside the main QDash Docker Compose project.
The API authenticates administrators, refuses updates while a calibration lock is held, and
forwards only fixed status and update operations over a Unix domain socket. The updater owns the
Git checkout, Docker Compose commands, persistent operation state, and rollback attempt, so
restarting the QDash API does not terminate an update.

Do not run the updater inside the main `compose.yaml`. Updating QDash stops and rebuilds that
Compose project. The updater must remain alive throughout that process.

## Release safety manifest

Automatic updates are allowed only when the target stable tag contains `update-manifest.json` with
these values:

```json
{
  "schema_version": 1,
  "automatic_update": true,
  "migration_mode": "compose"
}
```

Set `automatic_update` to `false` and explain the manual procedure in `notes` when a release needs
a backup, migration, or deployment step that `docker compose up -d --build` cannot perform safely.
The Admin UI will show the release as unavailable for automatic update.

## Starting QDash

Clone QDash in any directory. Start the updater and Compose directly with the tools already used by
QDash deployments:

```bash
uv run qdash-updater start
docker compose up -d --build
```

Go Task is optional. When it is installed, `task deploy`, `task deploy-local`, and
`task deploy-local-fake` automatically run the equivalent updater command before starting Compose.
No updater configuration or system service installation is required.

The updater uses the current repository as the installation directory and stores its socket, PID,
log, and operation state under `.tmp/qdash-updater/`. The main Compose file mounts that directory
into the API container. The socket is not reachable over TCP and needs no GitHub or shared bearer
token. Public QDash repositories fetch stable tags anonymously from the configured Git remote.

Use `uv run qdash-updater status` to check the process and `uv run qdash-updater stop` to stop it.
`uv run qdash-updater run` runs it in the foreground for troubleshooting. The equivalent Task
commands are `task updater-status`, `task updater-stop`, and `task updater`. Advanced deployments
can override `QDASH_UPDATER_REPOSITORY`,
`QDASH_UPDATER_RUNTIME_DIR`, `QDASH_UPDATER_SOCKET`, `QDASH_UPDATER_STATE_PATH`, or
`QDASH_UPDATER_HEALTH_URL` in `.env`, but these settings are optional.

## Update behavior

The Admin **System** tab shows the current exact release tag, latest stable tag, working-tree state,
and any blocking reason. Starting an update performs these steps:

1. Verify that QDash is on an exact stable tag and its tracked working tree is clean.
2. Fetch tags and validate the target release manifest.
3. Refuse the request if another update or a calibration is running.
4. Stop the API, UI, deployment service, and user-flow worker.
5. Check out the target tag in detached-HEAD mode and validate the Compose configuration.
6. Run `docker compose up -d --build`; the Compose-managed idempotent migration must complete.
7. Wait for the configured API health URL.

If checkout or deployment fails after changing revisions, the updater checks out the previous
commit and attempts to rebuild and restart it. This is a code rollback, not a database rollback.
A release that cannot safely run the previous code after migration must disable automatic updates
in its manifest and document a backup-based maintenance procedure.
