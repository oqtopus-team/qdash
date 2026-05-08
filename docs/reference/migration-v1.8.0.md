# Migration to v1.8.0

QDash v1.8.0 introduces immutable `user_id` fields while keeping `username` as the login name and display snapshot. Installations upgraded from v1.7.3 should run this migration once after deploying v1.8.0.

## What Changes

The migration backfills `user.user_id` and related denormalized user reference fields across project, collaboration, workflow, and calibration collections.

Existing `username` fields are retained. They continue to work as login names and historical display snapshots, so this migration does not rename users or change passwords.

Affected references include:

- Project ownership and membership: `owner_user_id`, `user_id`, `invited_by_user_id`
- Collaboration records: forum posts, issues, issue knowledge reviews, notifications, notes, cool-down wiring events
- Workflow and calibration records: backends, tasks, tags, flows, execution history, execution counters, chips, qubits, couplings, calibration notes, and history collections
- Task result moderation fields such as `excluded_by_user_id`

## Before Running

Run the command from an environment that has the v1.8.0 QDash code and the same MongoDB environment variables as the API service. The v1.7.3 code does not have this migration command.

In the Docker Compose deployment, this usually means running it inside an API container or an equivalent one-off maintenance container built from the v1.8.0 image.

```bash
docker compose exec api python -m qdash.dbmodel.migration backfill-user-id
```

The migration uses the same database initialization path as QDash. Confirm these environment variables point to the intended database before running:

- `MONGO_DB_NAME`
- `MONGO_INITDB_ROOT_USERNAME`
- `MONGO_INITDB_ROOT_PASSWORD`

Do not run the migration with `ENV=test`; QDash skips Bunnet initialization in test mode.

Stop application writes or run during a maintenance window. Block public API traffic and stop workflow workers, schedulers, and any scripts that write QDash data. Keep only the maintenance shell or container needed to run the migration. The migration is idempotent for already-filled `user_id` fields, but concurrent writes can leave newly-created documents without `user_id` until they are written by v1.8.0 code or the migration is rerun.

Take a MongoDB backup before executing the migration. Use the connection method that matches the deployment. For a URI-based environment:

```bash
mongodump --uri "$MONGODB_URL" --out ./backup-before-v1.8.0
```

For the local Docker Compose MongoDB service, run the equivalent backup against the configured database:

```bash
docker compose exec mongo mongodump \
  --username "$MONGO_INITDB_ROOT_USERNAME" \
  --password "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --db "$MONGO_DB_NAME" \
  --out /tmp/backup-before-v1.8.0
```

## Dry Run

Run the migration without `--execute` first.

```bash
python -m qdash.dbmodel.migration backfill-user-id
```

Review the logged statistics:

- `users_without_user_id`: users that need a generated internal ID
- `collections.*.matched`: documents that need a related `*_user_id`
- `unresolved`: username references that do not map to an existing user

`unresolved` entries should be reviewed before execution. They usually indicate historical rows for deleted users, system-generated authors, or inconsistent usernames.

If the command is run inside Docker Compose, use:

```bash
docker compose exec api python -m qdash.dbmodel.migration backfill-user-id
```

## Execute

Run the migration with `--execute` after the dry-run result looks correct.

```bash
python -m qdash.dbmodel.migration backfill-user-id --execute
```

The command generates IDs like `usr_<hex>` for users missing `user_id`, then fills related references from the username-to-user-id map.

For Docker Compose:

```bash
docker compose exec api python -m qdash.dbmodel.migration backfill-user-id --execute
```

## Verify

Run the dry-run command again. A clean result should have:

- `users_without_user_id: 0`
- no unexpected `collections.*.matched` counts
- no unexpected `unresolved` references

```bash
python -m qdash.dbmodel.migration backfill-user-id
```

Some `unresolved` rows can be acceptable if they refer to intentional pseudo-users or historical deleted users. They will remain unmatched on subsequent dry runs until those usernames are either recreated as users or the historical rows are handled manually.

Then restart the API, workers, schedulers, and UI services on v1.8.0. Login still uses `username`; users do not need to reset passwords because of this migration.

## Rollback Notes

The migration only adds `user_id` and `*_user_id` fields. Rolling the application back to v1.7.3 leaves those extra fields unused. If a full data rollback is required, restore the MongoDB backup taken before execution.
