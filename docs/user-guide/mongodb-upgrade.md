# Upgrade MongoDB

QDash v1.10.0 selects the MongoDB image from `MONGO_VERSION` in `.env`, as `mongo:<MONGO_VERSION>`,
and never changes the MongoDB release of existing data on its own. A new installation only copies
the `.env` example, as in [New Installations](#new-installations). A deployment with existing data
first pins the release it runs now, then upgrades MongoDB to 9.0 in a separate maintenance window,
starting at [Check and Pin the Running Release](#check-and-pin-the-running-release).

## Who Upgrades and When

The page applies to every deployment whose `MONGO_DATA_PATH` holds data written by MongoDB before
9.0.8:

- QDash v1.10.0, the current release, requires `MONGO_VERSION`. While it is missing or empty,
  every `docker compose` command fails before it creates a container, so QDash never chooses a
  release for existing data. QDash neither checks nor upgrades the MongoDB release at startup.
- QDash v1.11.0 is planned to make `mongo:9.0.8` the standard release. Upgrade MongoDB with this
  page after installing QDash v1.10.0 and before installing QDash v1.11.0, as described in
  [Update to QDash v1.11.0](#update-to-qdash-v1-11-0).

A checkout older than QDash v1.10.0 uses the unversioned `mongo` image, whatever image the Docker
host has tagged `mongo:latest`. A `docker compose pull`, or a host without that image, fetches the
newest MongoDB release, which can refuse data written by an older one. On such a checkout,
recreate MongoDB only after pinning its running release as in
[Pin the Running Release](#pin-the-running-release). After such a pull, read the release with
[Docker directly](#check-the-release-with-docker-directly).

The procedure covers the standalone `mongo` service of `compose.yaml`. For a replica set or a
sharded cluster, follow the official
[MongoDB 9.0 upgrade procedures](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-standalone/)
for that topology. Run every command from the QDash repository root.

## New Installations

A new installation that copies `.env` from a QDash v1.10.0 example as in
[Setup](./setup.md#create-the-environment-file) gets `MONGO_VERSION=9.0.8`, starts MongoDB `9.0.8`
on an empty `MONGO_DATA_PATH`, and creates its data at FCV `9.0`. It needs no migration and no
other step on this page. Keep `MONGO_VERSION=9.0.8` only for an empty data directory: data
written by an older release follows the procedure for existing deployments.

## Check and Pin the Running Release

An existing deployment sets the release it runs now once, before the update to QDash v1.10.0, as
in [Prepare the Update](./system-updates.md#prepare-the-update), so installing QDash v1.10.0 does
not change MongoDB. If the checkout or the images were already pulled, read the release with
[Docker directly](#check-the-release-with-docker-directly) instead.

### Check the Running Release

With QDash running, read the MongoDB release and its feature compatibility version (FCV), the
data format version that MongoDB writes. The command uses the credentials of the `mongo`
container:

```bash
docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"'
```

For a MongoDB without authentication, drop the `-u`, `-p`, and `--authenticationDatabase`
options here and in the later commands. The output is the release and the FCV, for example
`7.0.12` and `{ version: '7.0' }`. Later steps call this the status command.

### Check the Release with Docker Directly

Docker reads containers without the Compose files, so use it when Compose cannot read the
deployment. After `git pull` brings QDash v1.10.0 into a checkout whose `.env` has no
`MONGO_VERSION`, every `docker compose` command, including `docker compose ps` and
`docker compose exec`, fails with `required variable MONGO_VERSION is missing a value`.

A pull does not change a container. `git pull` changes `compose.yaml`, and `docker pull mongo` or
`docker compose pull` moves a tag such as `mongo:latest` to a newer image, but an existing
container keeps the image it was created from, identified by its image ID. The new release
reaches the data only when Compose recreates the container, as the next `docker compose up` does
after the image changed. Until the release is pinned, do not run `docker compose up`,
`docker compose pull`, or `docker compose down`.

1. List the MongoDB containers of all Compose projects:

   ```bash
   docker ps -a --filter label=com.docker.compose.service=mongo --format '{{.Names}}\t{{.Status}}\t{{.Label "com.docker.compose.project"}}'
   ```

2. Choose the container of the deployment's Compose project (normally `ENV` from `.env`, unless
   `-p` or `COMPOSE_PROJECT_NAME` overrides it), not the first one in the list. Confirm that its
   `com.docker.compose.project.working_dir` label is this checkout and that the source of its
   `/data/db` mount is the deployment's `MONGO_DATA_PATH`, and note its image ID:

   ```bash
   docker inspect <container> --format '{{.State.Status}} {{.Image}} {{json .Config.Labels}} {{json .Mounts}}'
   ```

3. If the container is running, print the release and FCV of the data it serves, with the
   container name in place of `<container>`. This is the release to pin:

   ```bash
   docker exec <container> sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"'
   ```

4. If the container is stopped, do not start it to find out: its data directory might have been
   used by a newer container since. Read the release from the image ID of step 2 instead. The
   image stays on the host while a container uses it, even after a pull moved its tag:

   ```bash
   docker image inspect <image-id> --format '{{json .Config.Env}}'
   ```

   The `MONGO_VERSION` entry is the release the image contains, the release this container ran.
   It says nothing about the FCV, and nothing about a container that used the same directory
   later. Pin it only when deployment records confirm that this container last wrote the data
   directory.

If no container of the project is listed, for example after `docker compose down` removed it,
use the release recorded before the update. If the image metadata is missing, the data history
is uncertain, or no release was recorded, do not guess one and do not start MongoDB on the data
with `9.0.8` or another release.

### Pin the Running Release

Pin MongoDB to the exact running release so that a recreated container keeps the same release.
QDash v1.10.0 and later require this line and have no fallback release. Change the existing
`MONGO_VERSION` line in `.env` to the release that the status command or the Docker check printed,
or add the line if it is missing:

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

## Choose the Upgrade Path

Find the row of the release and FCV that the status command printed. The upgrade later uses each
image of that row in order:

| Running release | FCV before the first step | Image of each step | FCV to set after the step |
| --- | --- | --- | --- |
| 7.0 | `7.0` | `mongo:8.0.38`, then `mongo:9.0.8` | `8.0` after `8.0.38` |
| 8.0 | `8.0` | `mongo:9.0.8` | None |
| 8.2 | `8.2` | `mongo:8.3.17`, then `mongo:9.0.8` | `8.3` after `8.3.17` |
| 8.3 | `8.3` | `mongo:9.0.8` | None |
| 9.0 before 9.0.8 | `8.0`, `8.3`, or `9.0` | `mongo:9.0.8`, a patch update | None |
| 9.0.8 or a later 9.0 patch | Any | None; keep the pinned release | None |

These are the newest patch releases of each series on
[Docker Hub](https://hub.docker.com/_/mongo/tags) as of 2026-11-13. Never use an image older than
the running release. Do not skip a step: each release opens only data whose FCV is at most one
step behind. For any other release, such as 6.0 or 8.1, find the path in the
[MongoDB release notes](https://www.mongodb.com/docs/manual/release-notes/) first. If the FCV is
lower than the running series, such as `6.0` on a 7.0 server, or shows a `targetVersion` field,
set it to the running series after the backup and before the first image change, with the FCV
command in step 4 of [Upgrade One Step at a Time](#upgrade-one-step-at-a-time).

## Back Up and Upgrade

Run the upgrade in a maintenance window, with QDash stopped from the backup until the last step
succeeds. The backup is a cold copy of the whole `MONGO_DATA_PATH` directory, the `/data/db` bind
mount of `mongo`, taken after MongoDB shut down cleanly. Copying the files while MongoDB runs does
not give a consistent backup. The copy holds the data files exactly as the running release wrote
them, so the same release opens them again at the same FCV. A logical backup with `mongodump` is
an alternative described in [MongoDB backup methods](https://www.mongodb.com/docs/manual/core/backups/);
this page does not use it.

### Stop Writers and Record the Deployment

1. Complete or cancel running calibrations and other workflows from **Execution**, and stop
   external clients that write to MongoDB.
2. Stop QDash, then start only MongoDB:

   ```bash
   docker compose stop --timeout 120
   docker compose up -d --no-deps --wait mongo
   ```

   `--no-deps` keeps every other service stopped until the upgrade succeeds.
3. Find the container, its immutable image ID, and the host directory of its `/data/db` mount,
   and choose a new backup directory next to it:

   ```bash
   MONGO_CONTAINER=$(docker compose ps -q mongo)
   MONGO_IMAGE_ID=$(docker inspect "$MONGO_CONTAINER" --format '{{.Image}}')
   MONGO_SOURCE=$(docker inspect "$MONGO_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/data/db"}}{{.Source}}{{end}}{{end}}')
   BACKUP="$MONGO_SOURCE.backup-$(date +%Y%m%d-%H%M%S)"
   echo "$MONGO_IMAGE_ID $MONGO_SOURCE $BACKUP"
   sudo ls "$MONGO_SOURCE"
   sudo du -sh "$MONGO_SOURCE"; df -h "$(dirname "$MONGO_SOURCE")"
   ```

   `MONGO_SOURCE` must be the host path of `MONGO_DATA_PATH`, and the listing must show
   `WiredTiger` and `mongod.lock`. The file system must have free space for two copies of the
   data, the backup and the restore test. Later steps use these variables; in a new shell, set
   them again to the values printed here.
4. Record the release, FCV, image, configuration, and the document count of each collection in
   the backup directory. The directory holds `.env` and its passwords, so only its owner can read
   it:

   ```bash
   sudo mkdir "$BACKUP" && sudo chown "$(id -u):$(id -g)" "$BACKUP" && chmod 700 "$BACKUP"
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"' > "$BACKUP/status.txt"
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "const d = db.getSiblingDB(\"${MONGO_DB_NAME:-qdash}\"); d.getCollectionNames().sort().forEach(c => print(c, d.getCollection(c).estimatedDocumentCount()))"' > "$BACKUP/counts.txt"
   printf 'image_id=%s\ndata_source=%s\n' "$MONGO_IMAGE_ID" "$MONGO_SOURCE" > "$BACKUP/deployment.txt"
   docker image inspect "$MONGO_IMAGE_ID" --format '{{json .Config.Env}}' >> "$BACKUP/deployment.txt"
   cp .env "$BACKUP/env"
   docker compose config > "$BACKUP/compose-config.yaml"
   cat "$BACKUP/status.txt"
   ```

   `status.txt` holds the original release and FCV, which the restore test and
   [Restore the Original Release](#restore-the-original-release) compare against.

### Back Up the Data Directory

1. Stop MongoDB and confirm that it shut down cleanly:

   ```bash
   docker compose stop --timeout 120 mongo
   docker inspect "$MONGO_CONTAINER" --format '{{.State.Status}} {{.State.ExitCode}}'
   sudo wc -c "$MONGO_SOURCE/mongod.lock"
   ```

   The output must be `exited 0`, then a size of `0` for `mongod.lock`. MongoDB empties
   `mongod.lock` on a clean shutdown; a non-empty file or another exit code means an unclean
   shutdown. In that case, do not copy:
   start MongoDB again with `docker compose up -d --no-deps --wait mongo`, check
   `docker compose logs --tail 100 mongo`, and repeat this step.
2. Copy the whole directory with its owners, modes, and timestamps into the backup directory:

   ```bash
   (
     set -e
     sudo test ! -e "$BACKUP/db"
     sudo test ! -L "$BACKUP/db"
     sudo cp -a "$MONGO_SOURCE" "$BACKUP/db"
     sudo diff -r "$MONGO_SOURCE" "$BACKUP/db"
     echo "backup matches"
   )
   ```

   Each copy destination must be absent, including symbolic links. If a destination check or
   copy fails, stop here and choose a fresh destination; do not continue with a partial or
   existing copy. The comparison must print `backup matches`. Keep MongoDB stopped until the restore test
   passes. The backup shares a disk with the data; also copy `$BACKUP` to other storage when
   that disk is the risk you need to cover.

### Test the Backup

Open a copy of the backup with the original image in a separate container, so the test never
touches the backup itself or the production data. The container has no network, no published
port, and no restart policy, and it starts without the root credentials, so MongoDB runs without
authentication and is reachable only from inside the container:

1. Copy the backup and start the test container from the recorded image ID:

   ```bash
   RESTORE_TEST="$BACKUP.restore-test"
   (
     set -e
     sudo test ! -e "$RESTORE_TEST"
     sudo test ! -L "$RESTORE_TEST"
     sudo cp -a "$BACKUP/db" "$RESTORE_TEST"
     docker run -d --name qdash-mongo-restore-test --network none -e MONGO_DB_NAME=qdash -v "$RESTORE_TEST":/data/db "$MONGO_IMAGE_ID"
     until docker exec qdash-mongo-restore-test mongosh --quiet --eval 'db.adminCommand({ping: 1}).ok' > /dev/null 2>&1; do sleep 2; done
   )
   ```

   Replace `qdash` with the `MONGO_DB_NAME` of `.env` if it differs. If the loop does not end
   within a minute, check `docker logs qdash-mongo-restore-test`.
2. Compare the release, FCV, and counts with the record:

   ```bash
   docker exec qdash-mongo-restore-test mongosh --quiet --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)" | diff "$BACKUP/status.txt" - && echo "status match"
   docker exec qdash-mongo-restore-test sh -c 'mongosh --quiet --eval "const d = db.getSiblingDB(\"$MONGO_DB_NAME\"); d.getCollectionNames().sort().forEach(c => print(c, d.getCollection(c).estimatedDocumentCount()))"' | diff "$BACKUP/counts.txt" - && echo "counts match"
   ```

   Both comparisons must print a match. If either fails, do not upgrade: keep `MONGO_VERSION`
   unchanged, start QDash again, and investigate the backup.
3. Remove the test container and its copy:

   ```bash
   docker stop --timeout 120 qdash-mongo-restore-test && docker rm -v qdash-mongo-restore-test
   sudo rm -rf "${RESTORE_TEST:?}"
   ```

### Upgrade One Step at a Time

Repeat these steps for each image in your row of the
[upgrade path table](#choose-the-upgrade-path), in order.

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
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "const d = db.getSiblingDB(\"${MONGO_DB_NAME:-qdash}\"); d.getCollectionNames().sort().forEach(c => print(c, d.getCollection(c).estimatedDocumentCount()))"' | diff "$BACKUP/counts.txt" - && echo "counts match"
   ```

   Run the status command too. It must print the release of this step, with the FCV unchanged.
   The comparison must print `counts match`, and the log must show no startup errors. If any
   check fails, stop and follow [Restore the Original Release](#restore-the-original-release).
4. If the table names an FCV after this step, set it and run the status command again:

   ```bash
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "printjson(db.adminCommand({setFeatureCompatibilityVersion: \"8.0\", confirm: true}))"'
   ```

   Replace `8.0` with the FCV of this step. The command must print `ok: 1`, and the status command
   must show that version with no `targetVersion`. If the command fails part way, run it again.

## Verify the Upgrade and Set the Final FCV

The upgrade is complete only when the status command prints the pinned 9.0 release, at least
`9.0.8`, and `{ version: '9.0' }` with no `targetVersion`. MongoDB 9.0 at FCV `8.0` or `8.3` is a
verification stage, not a finished upgrade: MongoDB 9.0 keeps the previous FCV until you raise
it, and features of 9.0 that change the data format stay disabled. The same applies to a
deployment that was already on a 9.0 release before this page.

1. Start QDash with the command the deployment normally uses, including its profiles, such as
   `docker compose up -d`, and check it as in
   [Verify the Deployment](./system-updates.md#verify-the-deployment).
2. Run the status command. It must print the pinned 9.0 release. If it already shows
   `{ version: '9.0' }` with no `targetVersion`, the upgrade is complete; skip the remaining
   steps.
3. Check normal operation while the FCV is still `8.0` or `8.3`, which MongoDB recommends before
   it is raised. Each check must succeed:

   - Sign in to QDash and open the pages your team uses, such as recent calibration results,
     and confirm that data from before the upgrade appears.
   - Run a calibration or another workflow that the team runs routinely from **Execution**, and
     confirm that it completes and that its results appear in QDash.
   - Run any external client that writes to MongoDB and confirm that its writes succeed.
   - Run `docker compose logs --tail 200 mongo` and confirm that the log shows no errors.

   The time that passes does not replace these checks. If a check fails, do not raise the FCV;
   investigate, or follow [Restore the Original Release](#restore-the-original-release).
4. After every check succeeds, set the FCV to `9.0`:

   ```bash
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "printjson(db.adminCommand({setFeatureCompatibilityVersion: \"9.0\", confirm: true}))"'
   ```

   The command must print `ok: 1`. If it fails part way, run it again until it prints `ok: 1`.
5. Confirm the final state:

   ```bash
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"'
   ```

   The output must be the pinned 9.0 release, such as `9.0.8`, and `{ version: '9.0' }`, with no
   `targetVersion` field. This completes the upgrade.

Keep `MONGO_VERSION` in `.env` at the pinned 9.0 release; QDash never changes it. Keep the
backup directory `$BACKUP` as well. After the FCV is `9.0`, a release older than 9.0 refuses to
start on the data, and this page does not cover returning the changed data to an older release.
Restoring the backup as in [Restore the Original Release](#restore-the-original-release) returns
the deployment to the original release, and every write made after the backup is lost.

## Example: Upgrade from 8.2

On 2026-11-16, one deployment upgraded from MongoDB `8.2.9` at FCV `8.2` with this page. The
example shows what each stage printed; it is a record of one run, not a separate procedure, and
it does not show that every workflow was tested. Each row is the output of the status command
after the step:

| Step | Release | FCV |
| --- | --- | --- |
| Before the upgrade | `8.2.9` | `{ version: '8.2' }` |
| Recreate `mongo` with `mongo:8.3.17` | `8.3.17` | `{ version: '8.2' }` |
| Set the FCV to `8.3` | `8.3.17` | `{ version: '8.3' }` |
| Recreate `mongo` with `mongo:9.0.8` | `9.0.8` | `{ version: '8.3' }` |
| Set the FCV to `9.0` after the checks | `9.0.8` | `{ version: '9.0' }` |

Before the first step, the cold copy of the stopped data directory printed `backup matches`, and
the original image opened a copy of it in the isolated test container with `status match` and
`counts match`. The operator reported that the interim count checks looked fine. With the
FCV still at `8.3`, the operator confirmed that QDash worked normally, then set the FCV to `9.0`;
the command printed `ok: 1`, and the final status showed no `targetVersion`. The deployment
keeps `MONGO_VERSION=9.0.8` and the original backup.

## Restore the Original Release

Restore the backup when an upgrade step fails, or when a check in
[Verify the Upgrade and Set the Final FCV](#verify-the-upgrade-and-set-the-final-fcv) fails and
you decide to return to the original release. Do not set `MONGO_VERSION` back to an older release
on the changed data in `MONGO_DATA_PATH`: once a newer release or FCV has written it, the older release
can refuse it or damage it. Restore a fresh copy of the backup instead, and keep the changed
data for investigation. Writes made after the backup are not in it; if QDash already ran on the
new release, those writes are lost.

1. Keep QDash stopped, or stop it with `docker compose stop --timeout 120`, and save the log:

   ```bash
   docker compose logs --no-color mongo > "$BACKUP/failed-upgrade.log"
   ```

2. Copy the backup into a new directory next to the changed data. The backup and the changed
   data stay as they are:

   ```bash
   MONGO_RESTORED="$MONGO_SOURCE.restored-$(date +%Y%m%d-%H%M%S)"
   (
     set -e
     sudo test ! -e "$MONGO_RESTORED"
     sudo test ! -L "$MONGO_RESTORED"
     sudo cp -a "$BACKUP/db" "$MONGO_RESTORED"
     echo "$MONGO_RESTORED"
   )
   ```

   Continue only if the copy succeeds and prints the new path. On failure, leave `.env`
   unchanged and choose a fresh destination before retrying.

3. In `.env`, set `MONGO_DATA_PATH` to the printed path and `MONGO_VERSION` to the original
   release, the first line of `$BACKUP/status.txt`, for example:

   ```dotenv
   MONGO_DATA_PATH="/srv/qdash/mongo_data/data/db.restored-20261116-120000"
   MONGO_VERSION=7.0.12
   ```

   On a checkout older than QDash v1.10.0, set the release in `compose.override.yaml` as in
   [Pin the Running Release](#pin-the-running-release). Confirm that Compose resolves the image
   and the mount:

   ```bash
   docker compose config --images | grep '^mongo:'
   docker compose config | grep -F "$MONGO_RESTORED"
   ```

4. Start MongoDB alone on the restored copy and compare it with the record:

   ```bash
   docker compose up -d --no-deps --force-recreate --wait mongo
   docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"' | diff "$BACKUP/status.txt" - && echo "status match"
   ```

   The comparison must print `status match`; then run the count comparison of step 3 of
   [Upgrade One Step at a Time](#upgrade-one-step-at-a-time), which must print `counts match`.
5. Start QDash with the command the deployment normally uses and check it as in
   [Verify the Deployment](./system-updates.md#verify-the-deployment).

Keep the changed data directory until the cause is understood, then delete it yourself. The
official [9.0 downgrade procedures](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade/)
are an alternative only when the writes since the backup must survive; they change the data in
place, so take a new backup with this page first and follow their prerequisites.

## Update to QDash v1.11.0

QDash v1.11.0 is planned to make `mongo:9.0.8` the standard MongoDB release for every deployment.
It does not migrate existing data and does not apply `9.0.8` to it silently, so upgrade MongoDB
with this page first. Keep `MONGO_VERSION` in `.env` at the running release until the v1.11.0
release notes describe the change. Before stopping QDash for that update as described in
[System Updates](./system-updates.md), confirm that the MongoDB release it selects is the release
that runs now or a later 9.0 patch. If it would select an older release, keep the running release
pinned and report the mismatch instead of downgrading.
