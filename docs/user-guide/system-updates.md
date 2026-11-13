# System Updates

Update a QDash source deployment from the host by selecting a stable release tag and rebuilding
the Docker Compose stack.

Run these commands from the QDash repository root. Schedule a maintenance window because QDash is
unavailable while its containers are stopped and rebuilt.

## Prepare the Update

Read the target release notes before changing the checkout. A release that changes stored data
can require a backup or a release-specific procedure.

1. Complete or cancel running calibrations and other workflows from **Execution**, and confirm
   that none is still running.
2. Back up MongoDB, PostgreSQL, calibration data, and Qubex configuration when required by the
   release notes or your recovery policy.
3. Record the MongoDB release that runs now, before you change the checkout or stop QDash.
   QDash v1.10.0 and later read it from `MONGO_VERSION` in `.env` and refuse to start without
   it. With QDash running, print the release:

   ```bash
   docker compose exec -T mongo sh -c 'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "db.version()"'
   ```

   The command uses the credentials inside the `mongo` container, so do not type them. For a
   MongoDB without authentication, drop the `--username`, `--password`, and
   `--authenticationDatabase` options. Set the printed release, such as `7.0.12`, in the existing
   `.env`: change its `MONGO_VERSION` line, or add one line if it has none:

   ```dotenv
   MONGO_VERSION=7.0.12
   ```

   Keep the existing `.env`. Do not copy an example over it or take `9.0.8` from an example: that
   value is for an empty `MONGO_DATA_PATH`. Do not run `docker compose pull` on a checkout older
   than QDash v1.10.0, which uses the unversioned `mongo` image. If Compose already reports that
   `MONGO_VERSION` is missing, see
   [Find the Release When Compose Fails](./mongodb-upgrade.md#find-the-release-when-compose-fails).
   After installing QDash v1.10.0, upgrade MongoDB to 9.0 as described in
   [Upgrade MongoDB](./mongodb-upgrade.md) before installing QDash v1.11.0.
4. Confirm that the checkout is on `main` and has no tracked changes:

   ```bash
   git branch --show-current
   git describe --tags --exact-match
   git status --short
   ```

   The branch command must print `main`. Record the version printed by the tag command in case a
   rollback is necessary. The status command must print nothing. Commit or preserve local changes
   before continuing.

## Select a Release

Fetch the release tags from `origin`:

```bash
git fetch origin --tags --prune
git tag --list 'v[0-9]*' --sort=-v:refname
```

Select a stable `vMAJOR.MINOR.PATCH` tag. Do not select a prerelease tag such as
`v2.0.0-rc.1`. Replace `<target-tag>` in the following steps with the selected tag.

Confirm that the target belongs to the stable branch before stopping QDash:

```bash
git merge-base --is-ancestor <target-tag> origin/main
```

The command must exit successfully. If it does not, do not deploy that tag.

## Deploy the Release

1. Stop QDash before advancing `main`:

   ```bash
   docker compose down
   ```

2. If the release moves the AI runtime to a newer Pi release, such as Pi 1.3 to 1.4 or Pi 1.4 to
   1.5, back up the stopped `agent-runtime-state` Docker volume now. The new Pi release migrates
   saved conversations when it first opens or writes them, and an earlier release cannot read the
   migrated volume. How this works:
   [Copilot architecture](../developer-guide/copilot/architecture.md#durable-conversations).
3. Advance `main` to the target without creating a merge commit, validate Compose, and rebuild:

   ```bash
   git merge --ff-only <target-tag>
   docker compose config --quiet
   docker compose up -d --build
   ```

`git merge --ff-only` refuses a divergent update instead of combining release code with local
commits. Resolve the branch state before retrying; do not force the merge.

## Verify the Deployment

Check the containers and browser-facing services after the build finishes:

```bash
docker compose ps
```

- QDash UI: <http://localhost:5714/login>
- API documentation: <http://localhost:5714/api/docs>
- Prefect: <http://localhost:5714/prefect/dashboard>

Use `UI_PORT` from `.env` if the deployment overrides the default. Follow service logs as
described in [Operations](./operations.md#inspect-logs) when a container is unhealthy or a page is
unavailable.

## Check Direct Service Access

When upgrading from a release without `caddy`, direct service connections must move to the
single `UI_PORT` entry point. Caddy routes `/api` and `/prefect`; other services expose no
host ports. No `.env` change is required, and `docker compose up -d` rebuilds the UI image.

Check what reached those services directly, from another machine or from the QDash host:

- Change a script, client, or proxy that called `API_PORT` or `PREFECT_PORT` to
  `http://<host>:<UI_PORT>/api` or `http://<host>:<UI_PORT>/prefect`. Prefect there requires a
  QDash sign-in in the browser.
- Run database tools inside the containers, as in
  [Open a Database Shell](./operations.md#open-a-database-shell), instead of connecting to
  `MONGO_PORT`, `POSTGRES_PORT`, or mongo-express on `MONGO_EXPRESS_PORT`.
- Remove a `compose.override.yaml` port mapping that publishes `UI_PORT` for the `ui` service;
  `caddy` now uses that port.
- A Cloudflare Tunnel or other HTTPS proxy that points to `UI_PORT` keeps working when
  `CLIENT_URL` is its `https://` URL, as [Enable Remote Access](./setup.md#enable-remote-access)
  sets it. QDash takes the HTTPS scheme from `CLIENT_URL`, not from the proxy's
  `X-Forwarded-Proto`, so the proxy must keep the public hostname in the `Host` header, as
  Cloudflare Tunnel does by default.

## Check Saved Workflows

Workflows saved before task calls list tasks by name and stop before they measure on a release
that requires task calls. QDash does not convert them; each workflow owner updates their own.
Before anyone edits them, copy the saved workflows from the checkout so every owner can compare
against the original:

```bash
cp -a src/qdash/workflow/user_flows user_flows-backup
```

After the update, each owner edits their workflows as described in
[Update a flow saved before task calls](./creating-workflows.md#update-a-flow-saved-before-task-calls)
and tests each one on the Fake backend before it measures on hardware again. Pipeline specs queued
before the update run after conversion, and a new version 1 spec is rejected with a converted
spec to submit instead. A spec whose one-qubit step still sets `mode` is not converted, queued or
new: set `execution_mode` on that step as the rejection message names, then submit it again. The full list of edits:
[Migrate Saved Flows](../developer-guide/workflow/task-calls.md#migrate-saved-flows).

## Recover from a Failed Update

Follow the target release notes when deployment fails after stored data changes. Moving the Git
checkout back does not reverse MongoDB, PostgreSQL, calibration-data, configuration, or AI
conversation changes. Restore the backups required by that release, and the
`agent-runtime-state` backup after a Pi migration, before starting the previous application
version.

If the failure occurs before stored data changes are applied and the release notes permit a
code-only rollback, move `main` back to the previously deployed stable tag and rebuild:

```bash
git reset --hard <previous-tag>
docker compose up -d --build
```

`git reset --hard` discards tracked changes. Confirm the target tag and preserve any local work
before running it.
