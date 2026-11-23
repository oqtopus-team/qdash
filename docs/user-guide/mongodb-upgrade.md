# Upgrade MongoDB

Pin the release that last wrote your data before updating QDash. Upgrade MongoDB separately,
with a tested backup and one supported release step at a time.

## Who Upgrades and When

This procedure covers the standalone `mongo` service in `compose.yaml`. Run commands from the
repository root, retaining your deployment's Compose files and profiles. For replica sets or
sharded clusters, follow MongoDB's topology-specific upgrade procedure.

QDash requires `MONGO_VERSION` in `.env` and does not migrate MongoDB automatically. Never start
a guessed image release on an existing data directory.

## New Installations

The example's `MONGO_VERSION=9.0.8` is for an empty `MONGO_DATA_PATH`. No migration is needed.
Existing data follows the procedure below.

## Check and Pin the Running Release

### Check the Running Release

Run this **status command** to record the server release and feature compatibility version (FCV):

```bash
docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"'
```

For an unauthenticated deployment, omit the authentication options throughout this page.

### Check the Release with Docker Directly

If Compose fails because `MONGO_VERSION` is missing, do not run Compose up, pull, or down yet.
Find the existing container without Compose:

```bash
docker ps -a --filter label=com.docker.compose.service=mongo --format '{{.Names}}\t{{.Status}}\t{{.Label "com.docker.compose.project"}}'
```

Choose this deployment's container. Inspect its project working-directory label, `/data/db`
source, and immutable image ID:

```bash
docker inspect <container> --format '{{.State.Status}} {{.Image}} {{json .Config.Labels}} {{json .Mounts}}'
```

For a running container, read its status:

```bash
docker exec <container> sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"'
```

For a stopped container, inspect the recorded image instead of starting it:

```bash
docker image inspect <image-id> --format '{{json .Config.Env}}'
```

Its `MONGO_VERSION` describes that image, not the data's FCV. Use it only if records confirm
that container was the last writer. If the container or data history is unknown, stop and
recover the deployment records; do not guess from `mongo:latest`.

### Pin the Running Release

Set `.env` to the exact observed release, for example:

```dotenv
MONGO_VERSION=7.0.12
```

On checkouts older than v1.10.0, also merge this pin into `compose.override.yaml` (or your last
selected Compose file), preserving its other settings:

```yaml
services:
  mongo:
    image: mongo:7.0.12
```

Remove that override after updating to a checkout that uses `MONGO_VERSION`. Shell variables
and Compose image overrides take precedence over `.env`. Confirm the resolved image:

```bash
docker compose config --images | grep '^mongo:'
```

It must match the pin. Do not retag `mongo:latest`, which other deployments may share.

## Choose the Upgrade Path

Use each image in order. These are pinned examples; do not downgrade a newer patch release.

| Current release | Required starting FCV | Images in order | Intermediate FCV change |
| --- | --- | --- | --- |
| 7.0 | `7.0` | `8.0.38`, then `9.0.8` | Set `8.0` after `8.0.38` |
| 8.0 | `8.0` | `9.0.8` | None |
| 8.2 | `8.2` | `8.3.17`, then `9.0.8` | Set `8.3` after `8.3.17` |
| 8.3 | `8.3` | `9.0.8` | None |
| Earlier 9.0 patch | `8.0`, `8.3`, or `9.0` | `9.0.8` | None |
| 9.0.8 or later 9.0 patch | Any | Keep the running release | None |

For other releases, consult the [MongoDB release notes](https://www.mongodb.com/docs/manual/release-notes/).
If FCV is below the running series or has `targetVersion`, finish that FCV transition after
backup and before changing the image. Final FCV `9.0` is set only after verification below.

## Back Up and Upgrade

Keep all writers stopped through backup and image upgrades. A cold backup must be copied only
after clean MongoDB shutdown.

### Stop Writers and Record the Deployment

Finish or cancel calibrations and stop external writers. Stop the stack and start MongoDB alone:

```bash
docker compose stop --timeout 120
docker compose up -d --no-deps --wait mongo
```

Record the container, image, data path, and a fresh backup destination:

```bash
MONGO_CONTAINER=$(docker compose ps -q mongo)
MONGO_IMAGE_ID=$(docker inspect "$MONGO_CONTAINER" --format '{{.Image}}')
MONGO_SOURCE=$(docker inspect "$MONGO_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/data/db"}}{{.Source}}{{end}}{{end}}')
BACKUP="$MONGO_SOURCE.backup-$(date +%Y%m%d-%H%M%S)"
echo "$MONGO_IMAGE_ID $MONGO_SOURCE $BACKUP"
sudo ls "$MONGO_SOURCE"
sudo du -sh "$MONGO_SOURCE"; df -h "$(dirname "$MONGO_SOURCE")"
```

Confirm the source is `MONGO_DATA_PATH` and contains `WiredTiger` and `mongod.lock`. Allow space
for both a backup and restore-test copy. Keep these variables for later steps.

Save status, counts, and configuration in the protected backup directory:

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

The backup contains credentials. Keep its permissions restricted.

### Back Up the Data Directory

Stop MongoDB and check shutdown:

```bash
docker compose stop --timeout 120 mongo
docker inspect "$MONGO_CONTAINER" --format '{{.State.Status}} {{.State.ExitCode}}'
sudo wc -c "$MONGO_SOURCE/mongod.lock"
```

Require `exited 0` and a zero-byte lock file. Otherwise restart only MongoDB, inspect its logs,
and retry clean shutdown before copying.

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

Require `backup matches`. On any copy error, stop and choose a fresh destination. Keep MongoDB
stopped until the restore test passes. Copy the backup to separate storage to protect against
a disk failure.

### Test the Backup

Test a copy with the original image, isolated from the network and production data:

```bash
RESTORE_TEST="$BACKUP.restore-test"
(
  set -e
  sudo test ! -e "$RESTORE_TEST"
  sudo test ! -L "$RESTORE_TEST"
  sudo cp -a "$BACKUP/db" "$RESTORE_TEST"
  docker run -d --name qdash-mongo-restore-test --network none -e MONGO_DB_NAME=qdash -v "$RESTORE_TEST":/data/db "$MONGO_IMAGE_ID"
  for attempt in $(seq 1 30); do
    if docker exec qdash-mongo-restore-test mongosh --quiet --eval 'db.adminCommand({ping: 1}).ok' > /dev/null 2>&1; then
      exit 0
    fi
    sleep 2
  done
  echo "Restore test did not become ready; inspect its logs." >&2
  exit 1
)
```

Replace `qdash` with your `MONGO_DB_NAME`. Continue only after a successful readiness check.
If it fails, inspect `docker logs qdash-mongo-restore-test` and resolve the failure before upgrading.

Compare the copied data with the recorded status and counts:

```bash
docker exec qdash-mongo-restore-test mongosh --quiet --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)" | diff "$BACKUP/status.txt" - && echo "status match"
docker exec qdash-mongo-restore-test sh -c 'mongosh --quiet --eval "const d = db.getSiblingDB(\"$MONGO_DB_NAME\"); d.getCollectionNames().sort().forEach(c => print(c, d.getCollection(c).estimatedDocumentCount()))"' | diff "$BACKUP/counts.txt" - && echo "counts match"
```

Both must match. Otherwise do not upgrade; retain the original pin and investigate. After success,
remove only the test container and its copy:

```bash
docker stop --timeout 120 qdash-mongo-restore-test && docker rm -v qdash-mongo-restore-test
sudo rm -rf "${RESTORE_TEST:?}"
```

### Upgrade One Step at a Time

For each image in the upgrade table:

1. Set `MONGO_VERSION` to that release and verify `docker compose config --images`.
2. Pull and recreate MongoDB alone:

```bash
docker compose pull mongo
docker compose stop --timeout 120 mongo
docker compose up -d --no-deps --wait mongo
```

3. Run the status command, then check logs and collection counts:

```bash
docker compose logs --tail 100 mongo
docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "const d = db.getSiblingDB(\"${MONGO_DB_NAME:-qdash}\"); d.getCollectionNames().sort().forEach(c => print(c, d.getCollection(c).estimatedDocumentCount()))"' | diff "$BACKUP/counts.txt" - && echo "counts match"
```

Require the new release, unchanged FCV, matching counts, and no startup errors. On failure,
[restore the original release](#restore-the-original-release).

4. When the table requires an intermediate FCV, set it (replace `8.0` as appropriate):

```bash
docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "printjson(db.adminCommand({setFeatureCompatibilityVersion: \"8.0\", confirm: true}))"'
```

Require `ok: 1`, then verify FCV with the status command. It must have no `targetVersion`.
If the transition is interrupted, finish it before the next image change.

## Verify the Upgrade and Set the Final FCV

1. Start QDash with its normal Compose files and profiles.
2. Confirm the pinned 9.0 release with the status command.
3. Before raising FCV, sign in, inspect pre-upgrade results, run a normal calibration, test
   external writers, and check MongoDB logs. Investigate any failure before proceeding.
4. If FCV is not already `9.0`, set it:

```bash
docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "printjson(db.adminCommand({setFeatureCompatibilityVersion: \"9.0\", confirm: true}))"'
```

5. Require `ok: 1`, then confirm the final state:

```bash
docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"'
```

The release must be the pinned 9.0 patch, at least `9.0.8`, and FCV must be `9.0` without
`targetVersion`. Keep the pin and backup. Restoring this backup loses every later write.

<a id="example-upgrade-from-8-2"></a>

## Restore the Original Release

Never start an older release on upgraded data. Restore a fresh copy of the backup and keep
the changed directory for investigation.

1. Stop the stack with `docker compose stop --timeout 120`, then save the log:

```bash
docker compose logs --no-color mongo > "$BACKUP/failed-upgrade.log"
```

2. Copy the backup to a new destination:

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

Continue only when the copy succeeds. Do not reuse a partial destination.

3. Set `.env` to the copied path and the original release from `$BACKUP/status.txt`, for example:

```dotenv
MONGO_DATA_PATH="/srv/qdash/mongo_data/data/db.restored-20261116-120000"
MONGO_VERSION=7.0.12
```

On an older checkout, also update its image override. Confirm both resolved settings:

```bash
docker compose config --images | grep '^mongo:'
docker compose config | grep -F "$MONGO_RESTORED"
```

4. Start MongoDB alone and compare status:

```bash
docker compose up -d --no-deps --force-recreate --wait mongo
docker compose exec -T mongo sh -c 'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "print(db.version()); printjson(db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion)"' | diff "$BACKUP/status.txt" - && echo "status match"
```

Require `status match`, then rerun the count comparison from the upgrade step and require
`counts match`.

5. Start QDash normally and [verify the deployment](./system-updates.md#verify-the-deployment).

Keep the changed data until the failure is understood. If post-backup writes must survive,
consult the [MongoDB downgrade procedure](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade/)
with a new backup instead of using this restore.

## Update to QDash v1.11.0

Follow that release's actual notes before updating. Confirm its selected MongoDB image matches
the running release or a later compatible patch; keep the pin if it would downgrade your data.
