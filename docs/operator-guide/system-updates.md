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

## Git branch and tag requirements

The installation directory is unrestricted, but the source checkout must meet these conditions:

- The current branch is `main`.
- `HEAD` is exactly at a stable tag named `vMAJOR.MINOR.PATCH`.
- The tracked worktree has no local modifications.
- The configured Git remote, `origin` by default, provides a newer stable tag.
- The target tag contains a manifest that permits automatic updates.

The updater compares tags using semantic version order and considers only stable tags in the
`origin/main` history. It ignores untagged commits, prerelease tags such as `v2.0.0-rc.1`, and tags
that do not match the stable version format. A successful update fast-forwards the local `main`
branch to the selected tag. It never merges a divergent branch or updates `develop` or a feature
branch.

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

Clone QDash in any directory and check out the `main` release branch according to
[Operator Setup](./setup.md#clone-the-repository). Start the updater and Compose directly with the
tools already used by QDash deployments:

```bash
uv run --env-file .env --isolated --locked --no-dev qdash-updater start
docker compose up -d --build
```

Go Task is optional. When it is installed, `task deploy`, `task deploy-local`, and
`task deploy-local-fake` automatically run the equivalent updater command before starting Compose.
No updater configuration or system service installation is required.

The updater uses the current repository as the installation directory and stores its socket, PID,
log, and operation state under `${XDG_STATE_HOME}/qdash/updater/`, or
`~/.local/state/qdash/updater/` when `XDG_STATE_HOME` is unset. The main Compose file mounts that
directory into the API container. Keeping runtime files outside the checkout prevents ownership
conflicts when the same checkout is used from both the host and a devcontainer. The socket is not
reachable over TCP and needs no GitHub or shared bearer token. Public QDash repositories fetch
stable tags anonymously from the configured Git remote.

The `--isolated` option is intentional. It keeps the host updater out of the repository's `.venv`,
which may have been created inside a devcontainer with a different interpreter or file owner.
`--locked --no-dev` uses the committed dependency versions without installing development tools.

Use `uv run --env-file .env --isolated --locked --no-dev qdash-updater status` to check the process
and `uv run --env-file .env --isolated --locked --no-dev qdash-updater stop` to stop it. Replace
`status` with `run` to run it in the foreground for troubleshooting. The equivalent Task commands are
`task updater-status`, `task updater-stop`, and `task updater`. Advanced deployments can override
`QDASH_UPDATER_REPOSITORY`,
`QDASH_UPDATER_RUNTIME_DIR`, `QDASH_UPDATER_SOCKET`, `QDASH_UPDATER_STATE_PATH`, or
`QDASH_UPDATER_HEALTH_URL` in `.env`, but these settings are optional.

## Update behavior

The Admin **System** tab shows the current exact release tag, latest stable tag, tracked worktree
state, and any blocking reason. Starting an update performs these steps:

1. Verify that QDash is on `main`, at an exact stable tag, with a clean tracked working tree.
2. Fetch tags and validate the target release manifest.
3. Refuse the request if another update or a calibration is running.
4. Stop the API, UI, deployment service, and user-flow worker.
5. Fast-forward `main` to the target tag and validate the Compose configuration.
6. Run `docker compose up -d --build`; the Compose-managed idempotent migration must complete.
7. Wait for the configured API health URL.

If checkout or deployment fails after changing revisions, the updater checks out the previous
commit and attempts to rebuild and restart it. This is a code rollback, not a database rollback.
A release that cannot safely run the previous code after migration must disable automatic updates
in its manifest and document a backup-based maintenance procedure.
