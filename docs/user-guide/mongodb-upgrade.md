# Upgrade MongoDB

QDash v1.10.0 selects the MongoDB image from `MONGO_VERSION` in `.env`, as `mongo:<MONGO_VERSION>`.
The setting is required: while it is missing or empty, every `docker compose` command fails
before it creates a container, so QDash never chooses a release for existing data. The `.env`
examples set `MONGO_VERSION=9.0.8` for a new installation. An existing deployment sets the
release it runs now once, before the update, as in
[Prepare the Update](./system-updates.md#prepare-the-update), so installing QDash v1.10.0 does not
change MongoDB. QDash neither checks nor upgrades the MongoDB release at startup. After installing
QDash v1.10.0, schedule a separate maintenance window in each deployment with existing data to
upgrade MongoDB to 9.0, release `9.0.8`, with the procedure on this page before you install QDash
v1.11.0.

A checkout older than QDash v1.10.0 uses the unversioned `mongo` image, whatever image the Docker
host has tagged `mongo:latest`. A `docker compose pull`, or a host without that image, fetches the
newest MongoDB release, which can refuse data written by an older one. On such a checkout,
recreate MongoDB only after pinning its running release as in
[Pin the Running Release](#pin-the-running-release).

The procedure covers the standalone `mongo` service of `compose.yaml`. For a replica set or a
sharded cluster, follow the official
[MongoDB 9.0 upgrade procedures](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-standalone/)
for that topology. Run every command from the QDash repository root.

## New Installations

A new installation that copies `.env` from a QDash v1.10.0 example as in
[Setup](./setup.md#create-the-environment-file) starts MongoDB `9.0.8` on an empty
`MONGO_DATA_PATH` and creates its data at FCV `9.0`. It needs no step on this page. Keep
`MONGO_VERSION=9.0.8` only for an empty data directory: data written by an older release follows
the upgrade steps below.

## Check the Running Release

With QDash running, read the MongoDB release and its feature compatibility version (FCV), the
data format version that MongoDB writes. The command uses the credentials of the `mongo`
container:

```bash
docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"'
```

The output is the release and the FCV, for example `7.0.12` and `{ version: '7.0' }`. Later steps
call this the status command. Find your path:

| Running release | FCV before the first step | Image of each step | FCV to set after the step |
| --- | --- | --- | --- |
| 7.0 | `7.0` | `mongo:8.0.38`, then `mongo:9.0.8` | `8.0` after `8.0.38` |
| 8.0 | `8.0` | `mongo:9.0.8` | None |
| 8.2 | `8.2` | `mongo:8.3.17`, then `mongo:9.0.8` | `8.3` after `8.3.17` |
| 8.3 | `8.3` | `mongo:9.0.8` | None |
| 9.0 before 9.0.8 | `8.0`, `8.3`, or `9.0` | `mongo:9.0.8`, a patch update | None |
| 9.0.8 or a later 9.0 patch | Any | None; pin the running release | None |

These are the newest patch releases of each series on
[Docker Hub](https://hub.docker.com/_/mongo/tags) as of 2026-11-13. Never use an image older than
the running release. Do not skip a step: each release opens only data whose FCV is at most one
step behind. For any other release, such as 6.0 or 8.1, find the path in the
[MongoDB release notes](https://www.mongodb.com/docs/manual/release-notes/) first. If the FCV is
lower than the running series, such as `6.0` on a 7.0 server, or shows a `targetVersion` field,
set it to the running series first with the FCV command in
[Upgrade One Step at a Time](#upgrade-one-step-at-a-time).

## Pin the Running Release

Pin MongoDB to the exact running release so that a recreated container keeps the same release.
QDash v1.10.0 and later require this line, which
[Prepare the Update](./system-updates.md#prepare-the-update) sets. Change the existing
`MONGO_VERSION` line in `.env` to the release that the status command printed, or add the line if
it is missing:

```dotenv
MONGO_VERSION=7.0.12
```

A checkout older than QDash v1.10.0 ignores `MONGO_VERSION`; there `compose.yaml` shows
`image: mongo` without `${MONGO_VERSION`. Until its update to QDash v1.10.0 or later, also add the
same release to `compose.override.yaml` next to `compose.yaml`, which Docker Compose loads
automatically, or to the last file of the selection when the deployment selects Compose files
with `-f` or `COMPOSE_FILE`. Merge into existing `services:` and `mongo:` entries, create the file
if it does not exist, and do not overwrite other settings:

```yaml
services:
  mongo:
    image: mongo:7.0.12
```

Remove this line after the checkout reaches QDash v1.10.0, so that `.env` alone selects the
release. An `image` line for `mongo` in `compose.override.yaml` or another Compose file overrides
`MONGO_VERSION`, and a `MONGO_VERSION` set in the shell overrides `.env`. Keep the deployment's
Compose file selection and `--profile` options in every command below. Do not retag
`mongo:latest`: other projects on the Docker host share that tag. Confirm the image Compose resolves:

```bash
docker compose config --images | grep '^mongo:'
```

The command must print the pinned image.

## Stop Writers and Back Up

1. Complete or cancel running calibrations and other workflows from **Execution**, and stop
   external clients that write to MongoDB.
2. Stop QDash, then start only MongoDB:

   ```bash
   docker compose stop --timeout 120
   docker compose up -d --no-deps --wait mongo
   ```

   `--no-deps` keeps every other service stopped until the upgrade succeeds.
3. Take a consistent backup of MongoDB with the method your organization already uses, such as
   `mongodump` or a copy of `MONGO_DATA_PATH` taken while MongoDB is stopped; see
   [MongoDB backup methods](https://www.mongodb.com/docs/manual/core/backups/). Without a backup,
   nothing guarantees a way back: once a newer FCV is set, the older release cannot open the data.
4. Record the document count of each collection, to compare after each step:

   ```bash
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "const d = db.getSiblingDB(\"${MONGO_DB_NAME:-qdash}\"); d.getCollectionNames().sort().forEach(c => print(c, d.getCollection(c).estimatedDocumentCount()))"' > mongo-counts-before.txt
   ```

## Upgrade One Step at a Time

Repeat these steps for each image in your row of the table, in order.

1. Change `MONGO_VERSION` in `.env` to the release of this step, for example
   `MONGO_VERSION=8.0.38`, and confirm it with
   `docker compose config --images | grep '^mongo:'`.
2. Pull the image and recreate `mongo` alone with it:

   ```bash
   docker compose pull mongo
   docker compose stop --timeout 120 mongo
   docker compose up -d --no-deps --wait mongo
   ```

3. Check the release, the log, and the data:

   ```bash
   docker compose logs --tail 100 mongo
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "const d = db.getSiblingDB(\"${MONGO_DB_NAME:-qdash}\"); d.getCollectionNames().sort().forEach(c => print(c, d.getCollection(c).estimatedDocumentCount()))"' | diff mongo-counts-before.txt - && echo "counts match"
   ```

   Run the status command too. It must print the release of this step, with the FCV unchanged.
   The comparison must print `counts match`, and the log must show no startup errors.
4. If the table names an FCV after this step, set it and run the status command again:

   ```bash
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "printjson(db.adminCommand({setFeatureCompatibilityVersion: \"8.0\", confirm: true}))"'
   ```

   Replace `8.0` with the FCV of this step. The command must print `ok: 1`, and the status command
   must show that version with no `targetVersion`. If the command fails part way, run it again.

After the last step, start QDash with the command the deployment normally uses, including its
profiles, such as `docker compose up -d`, and check it as in
[Verify the Deployment](./system-updates.md#verify-the-deployment).

## Set the Final FCV

If the status command already shows FCV `9.0` with no `targetVersion`, only verify that the
running release matches the pinned 9.0 release, at least `9.0.8`; no FCV change is needed.

After a series upgrade, MongoDB 9.0 keeps the previous FCV, `8.0` or `8.3`, until you raise it.
Keep it there for a burn-in period while QDash runs normally; until then, the official
[9.0 downgrade procedures](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade/) still
apply. Then run the FCV command of step 4 with `9.0` and confirm that the status command prints
the pinned running 9.0 release (at least `9.0.8`) and `{ version: '9.0' }`. After this, only a backup returns the data to an older release.

## If a Step Fails

Stop and keep QDash stopped. Do not set `MONGO_VERSION` back to an older release on the chance
that it opens the data: after a newer FCV is set, it cannot. Read `docker compose logs mongo`, then
recover with the official
[downgrade procedures](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade/) for your
release or by restoring the backup with your organization's method, and keep `MONGO_VERSION` at
the release that opens the restored data.

## Find the Release When Compose Fails

When `.env` has no `MONGO_VERSION`, Compose prints
`required variable MONGO_VERSION is missing a value` for every command, including
`docker compose ps` and `docker compose exec`. Read the release with Docker directly. List the
MongoDB containers of all Compose projects:

```bash
docker ps -a --filter label=com.docker.compose.service=mongo --format '{{.Names}}\t{{.Status}}\t{{.Label "com.docker.compose.project"}}'
```

Choose the container for the deployment's actual Compose project (normally `ENV` from `.env`,
unless `-p` or `COMPOSE_PROJECT_NAME` overrides it). Inspect its labels and mounts to confirm
the checkout and `MONGO_DATA_PATH`; do not choose the first container in the list:

```bash
docker inspect <container> --format '{{json .Config.Labels}} {{json .Mounts}}'
```

For a running container, print its release with the container name in place of `<container>`:

```bash
docker exec <container> sh -c 'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "db.version()"'
```

Do not start a stopped container to discover its version: its data directory might have been
used by a newer container. Inspect its immutable image ID, then that image's metadata offline:

```bash
docker inspect <container> --format '{{.Image}}'
docker image inspect <image-id> --format '{{json .Config.Env}}'
```

The `MONGO_VERSION` entry identifies the image's release. Use it only when deployment records
confirm this container last wrote the selected data directory. If the image metadata is missing
or the data history is uncertain, stop and recover the recorded release before proceeding.

Set the printed release as `MONGO_VERSION` in `.env`. If no container of the project is listed,
for example after `docker compose down` removed it, use the release recorded before the update.
Without a recorded release, do not guess one and do not start MongoDB on the data with
`9.0.8` or another release.

## Update to QDash v1.11.0

QDash v1.11.0 is planned to make `mongo:9.0.8` the standard MongoDB release for every deployment.
It does not migrate existing data and does not apply `9.0.8` to it silently, so upgrade MongoDB
with this page first. Keep `MONGO_VERSION` in `.env` at the running release until the v1.11.0
release notes describe the change. Before stopping QDash for that update as described in
[System Updates](./system-updates.md), confirm that the MongoDB release it selects is the release
that runs now or a later 9.0 patch. If it would select an older release, keep the running release
pinned and report the mismatch instead of downgrading.
