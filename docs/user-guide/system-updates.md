# System Updates

Update a QDash source deployment from the host by selecting a stable release tag and rebuilding
the Docker Compose stack.

Run these commands from the QDash repository root. Schedule a maintenance window because QDash is
unavailable while its containers are stopped and rebuilt.

## Prepare the Update

Read the target release notes before changing the checkout. A release that changes stored data
can require a backup or a release-specific procedure.

1. Confirm that no calibration or other workflow is running.
2. Complete or cancel running work from the QDash execution pages.
3. Back up MongoDB, PostgreSQL, calibration data, and Qubex configuration when required by the
   release notes or your recovery policy.
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

Stop QDash, advance `main` to the target without creating a merge commit, validate Compose, and
rebuild the stack:

```bash
docker compose down
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
- API documentation: <http://localhost:5715/docs>
- Prefect: <http://localhost:4200>

Use the ports from `.env` if the deployment overrides the defaults. Follow service logs as
described in [Operations](./operations.md#inspect-logs) when a container is unhealthy or a page is
unavailable.

## Recover from a Failed Update

Follow the target release notes when deployment fails after stored data changes. Moving the Git
checkout back does not reverse MongoDB, PostgreSQL, calibration-data, or configuration changes.
Restore the backups required by that release before starting the previous application version.

If the failure occurs before stored data changes are applied and the release notes permit a
code-only rollback, move `main` back to the previously deployed stable tag and rebuild:

```bash
git reset --hard <previous-tag>
docker compose up -d --build
```

`git reset --hard` discards tracked changes. Confirm the target tag and preserve any local work
before running it.
