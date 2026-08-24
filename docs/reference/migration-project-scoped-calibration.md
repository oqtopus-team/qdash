# Project-Scoped Calibration Migration

QDash now shares current calibration state among all members of a project. The deployment process
runs this migration automatically before the API, deployment service, and user-flow worker start.

The migration changes the unique ownership of chips, qubits, couplings, calibration notes, their
daily histories, and execution counters from a project-and-user key to a project-and-chip key.
`username` and `user_id` remain on documents as actor snapshots; they no longer partition
calibration state.

## Deployment behavior

`docker compose up` starts the one-shot `calibration-migration` service after MongoDB becomes
healthy. Other QDash services start only when the migration exits successfully. The migration is
idempotent and records completion as `project-scoped-calibration-v1` in `migration_ledger`.
Artifact migration is recorded separately as
`project-scoped-calibration-artifacts-date-layout-v2`, preventing legacy files from being
reconsidered after shared classifier files receive newer updates.
The migration lock has a 30-minute lease, so a deployment interrupted by a hard container stop can
recover automatically on a later deployment.
An idempotent compound index on migration ID, source collection, source document ID, and migration
kind keeps archive lookups bounded as `migration_archive` grows. Deployments install this index
even when the data migration ledger is already complete.

To inspect an installation without changing it, run:

```bash
docker compose run --rm calibration-migration \
  python -m qdash.dbmodel.migration project-scoped-calibration
```

Normal `task deploy` and `task deploy-local` runs execute the migration automatically with
`--execute`.

## Duplicate handling

For duplicate current or daily-history documents, QDash retains the latest document as the base.
Qubit and coupling parameters are merged by parameter name, preferring each parameter's latest
`calibrated_at` value and falling back to the document update time. Calibration-note mappings are
merged recursively in document update order. A stable document-ID comparison breaks exact
timestamp ties. Every losing document is copied verbatim to `migration_archive` before deletion.

Duplicate execution counters keep the largest issued index so a migrated project does not reuse an
execution ID. The other counter documents are archived in the same way.

The migration never deletes legacy calibration files. It copies execution artifacts to:

```text
calib_data/projects/{project_id}/chips/{chip_id}/executions/{date}/{index}/
```

After an execution directory is copied successfully, the migration rewrites its persisted artifact
references in `execution_history`, `task_result_history`, and `issue_knowledge` to the new project
path. Installations that already copied artifacts to `executions/{execution_id}` atomically move
that intermediate directory into the date layout when the destination does not exist, avoiding a
second full artifact copy. Every affected database document is copied verbatim to
`migration_archive` before its paths are changed. This keeps historical figures, raw data
downloads, and reanalysis available after the legacy directories are eventually removed.

Classifier files are copied to:

```text
calib_data/projects/{project_id}/chips/{chip_id}/shared/classifier/
```

When two legacy classifier files have the same relative path and different content, the file with
the latest modification time is retained at the shared destination and the other file is copied
below `.migration_conflicts/{username}`.

Execution artifacts missing from their expected legacy directories are recorded in the artifact
migration ledger and emitted as a warning. The report includes the execution ID, status, username,
stored calibration path, and paths checked so operators can distinguish expected gaps from files
that need recovery. Missing artifacts do not block the rest of QDash from starting because the
migration has already moved every artifact it could locate.

After reviewing the warning, an operator can rerun the migration with the following flag to mark
the missing artifacts as reviewed in the report:

```bash
docker compose run --rm calibration-migration \
  python -m qdash.dbmodel.migration project-scoped-calibration \
  --execute --allow-missing-artifacts
```

For legacy calibration documents missing `project_id`, the migration first resolves the actor by
`user_id` or `username`. It uses the user's `default_project_id` when available, or a single
active project membership when no default is stored. The original document is copied to
`migration_archive` under `project-scoped-calibration-scope-backfill-v1` before the resolved
project is written.

For legacy calibration notes missing `chip_id`, the migration resolves the chip when
`project_id + execution_id` identifies execution history for exactly one chip. The note remains
unresolved if no matching execution exists or multiple chips match.

Documents without a default and with multiple possible active projects, with no resolvable project,
or with another missing scope field still stop the migration and must be corrected before retrying.
They are never grouped under an implicit null project, and fields such as `qid`, `recorded_date`,
and `execution_id` are not inferred.

## Verification and recovery

After deployment, verify that `calibration-migration` exited with status zero and that the API and
worker services started. The legacy `calib_data/{username}` directories remain available for
rollback. Database documents removed during consolidation remain in `migration_archive`, including
their original `_id`, source collection, selected winner, and full document content.

Take a MongoDB and calibration-data backup before upgrading a production installation. Restoring
that backup is the supported full rollback if calibration ownership must return to the prior model.
