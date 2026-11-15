# System Updates

Update QDash by selecting `main` or a release tag in its Git repository, then running the
deployment command for your environment.

Run these commands from the QDash repository root. Deployment rebuilds and recreates services,
so finish running calibrations before updating.

## Prepare the Update

Read the target release notes for any required configuration changes, backups, or migrations.
Keep your existing `.env`, configuration, and data. Preserve local source changes before
switching versions.

For the first update to **v1.10.0**, set `MONGO_VERSION` to the MongoDB version already running,
as described in [Check and Pin the Running Release](./mongodb-upgrade.md#check-and-pin-the-running-release).
After deploying QDash v1.10.0, follow [Upgrade MongoDB](./mongodb-upgrade.md) to upgrade to 9.0
through the required intermediate versions and FCV steps. These are one-time upgrade actions. Follow the
v1.10.0 release notes for calibration-data migration, saved workflow changes, and AI configuration.
If a Pi runtime upgrade migrates existing conversations, back up the stopped `agent-runtime-state`
volume first; see [durable conversations](../developer-guide/copilot/architecture.md#durable-conversations).

## Select a Version

Fetch the available branches and tags:

```bash
git fetch origin --tags
```

Choose **one** of the following:

- To use the latest `main`:

  ```bash
  git switch main
  git pull --ff-only origin main
  ```

- To use a specific release, replace `v1.10.0` with the desired tag:

  ```bash
  git switch --detach v1.10.0
  ```

A detached checkout is expected when deploying a tag. To return to `main` later, use the first
option. If Git reports conflicting local changes or a divergent branch, resolve them before
deploying.

## Deploy the Release

Run the command that matches your existing deployment:

| Deployment | Command |
| --- | --- |
| Docker Compose without the bundled Cloudflare Tunnel | `task deploy-local` |
| Docker Compose with the bundled Cloudflare Tunnel configured | `task deploy` |

Both commands update the configured Copilot knowledge repository and rebuild and start the
Compose stack. `task deploy` also enables the `tunnel` profile and restarts the API after startup.
You do not need to stop and remove the stack first for a routine update.

Without Go Task, rebuild and start the Compose stack directly:

```bash
docker compose up -d --build
```

Retain the Compose files and profiles your deployment uses. This direct command does not update
the optional knowledge repository or add the Tunnel profile.

## Verify the Deployment

Check that services are running, then open QDash:

```bash
docker compose ps
```

- QDash UI: <http://localhost:5714/login>
- API documentation: <http://localhost:5714/api/docs>
- Prefect: <http://localhost:5714/prefect/dashboard>

Use your configured public URL or `UI_PORT` if it differs. If a service fails to start, inspect
its logs as described in [Operations](./operations.md#inspect-logs).

## Check Direct Service Access

When updating from a release without Caddy, change direct API and Prefect connections to
`http://<host>:<UI_PORT>/api` and `http://<host>:<UI_PORT>/prefect`. Only `UI_PORT` is published;
use [database shells inside the containers](./operations.md#open-a-database-shell) for database
access. Remove any Compose override that publishes `UI_PORT` on the `ui` service, because Caddy
now owns it. Existing proxies targeting `UI_PORT` can keep that address; follow
[remote access setup](./setup.md#enable-remote-access) for the public URL and hostname settings.

## Recover from a Failed Update

Check the release-specific recovery instructions before selecting an earlier tag and deploying
again. Changing the checkout does not reverse stored-data or AI conversation migrations; restore
the corresponding backups when the release requires them.
