# Upgrade MongoDB

After installing this QDash release, schedule a separate maintenance window in each deployment to
upgrade MongoDB to 9.0, release `9.0.8`, before you install the next QDash release. The next
release pins the MongoDB image in `compose.yaml`. This release still uses the unversioned `mongo`
image, and QDash neither checks nor upgrades the MongoDB release at startup, so each deployment
moves its own data with the procedure on this page.

The unversioned `mongo` image is whatever image the Docker host has tagged `mongo:latest`. A
`docker compose pull`, or a host without that image, fetches the newest MongoDB release, which can
refuse data written by an older one. Until the upgrade, recreate MongoDB only after pinning its
running release as in [Pin the Running Release](#pin-the-running-release).

The procedure covers the standalone `mongo` service of `compose.yaml`. For a replica set or a
sharded cluster, follow the official
[MongoDB 9.0 upgrade procedures](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-standalone/)
for that topology. Run every command from the QDash repository root.

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

Pin MongoDB to the exact running release in the Compose file this deployment already loads, so that
a recreated container keeps the same release. Docker Compose loads `compose.override.yaml` next to
`compose.yaml` automatically. Add the `image` line to it, merging into existing `services:` and
`mongo:` entries; create the file if it does not exist, and do not overwrite other settings:

```yaml
services:
  mongo:
    image: mongo:7.0.12
```

Use the release that the status command printed. If the deployment selects Compose files with
`-f` or `COMPOSE_FILE`, put the line in the last file of that selection instead, and keep using the
same selection and `--profile` options in every command below. Do not retag `mongo:latest`: other
projects on the Docker host share that tag. Confirm the image Compose resolves:

```bash
docker compose config --images | grep '^mongo:'
```

The command must print the pinned image. This override is a temporary migration tool, not a
permanent organization change; [After the Next QDash Release](#after-the-next-qdash-release)
removes it.

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

1. Change the `image` line of the override to the image of this step, for example
   `image: mongo:8.0.38`, and confirm it with
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

Stop and keep QDash stopped. Do not set the `image` line back to an older release on the chance
that it opens the data: after a newer FCV is set, it cannot. Read `docker compose logs mongo`, then
recover with the official
[downgrade procedures](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade/) for your
release or by restoring the backup with your organization's method, and keep the override at the
release that opens the restored data.

## After the Next QDash Release

Keep the current MongoDB `image` override until you install the QDash release that pins MongoDB in
`compose.yaml`. When you update to it as described in [System Updates](./system-updates.md), read
the pinned image before stopping QDash:

```bash
git show <target-tag>:compose.yaml | grep -A1 '^  mongo:'
```

Remove the override line only if that image is the release that runs now or a later 9.0 patch,
and confirm with `docker compose config --images | grep '^mongo:'` before starting QDash. If the
pinned image is older than the running release, keep the override and report the mismatch instead
of downgrading. Removing the line returns the deployment to the shared Compose configuration, with
no MongoDB difference kept per organization.
