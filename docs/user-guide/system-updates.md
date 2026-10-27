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

Stop QDash before advancing `main`:

```bash
docker compose down
```

When upgrading a Copilot deployment from Pi 1.3 to Pi 1.4, back up the stopped
`agent-runtime-state` Docker volume before continuing. Pi 1.4 migrates saved conversations when
the new runtime first opens them. A previous release cannot read the migrated volume; restore the
pre-update volume backup before starting that release during a rollback. How this works:
[Copilot architecture](../developer-guide/copilot/architecture.md#durable-conversations).

Advance `main` to the target without creating a merge commit, validate Compose, and rebuild:

```bash
git merge --ff-only <target-tag>
docker compose config --quiet
docker compose up -d --build
```

`git merge --ff-only` refuses a divergent update instead of combining release code with local
commits. Resolve the branch state before retrying; do not force the merge.

If the deployment uses the HTTPS override, include the same file arguments in each Compose command
before and after the update. Keep the release change between the stop and validation commands:

```bash
docker compose -f compose.yaml -f compose.https.yaml down
git merge --ff-only <target-tag>
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml up -d --build
```

Use only overrides present in both the current and target release. Keep the `-f` list identical
for each command in that release so Compose does not target a different stack.

## Verify the Deployment

Check the containers and browser-facing services after the build finishes:

```bash
docker compose ps
```

- QDash UI: <http://localhost:5714/login>
- API documentation: <http://localhost:5714/api/docs>
- Prefect dashboard: <http://localhost:5714/prefect/dashboard>

Use the configured `UI_PORT` if the deployment overrides the default Caddy port. The normal
Compose stack publishes no direct API or Prefect ports. Follow service logs as described in
[Operations](./operations.md#inspect-logs) when a container is unhealthy or a page is unavailable.
For HTTPS deployments, open the origin configured in `CLIENT_URL`; the `localhost:5714` links
above describe the default HTTP configuration.

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

For an HTTPS deployment, include `-f compose.yaml -f compose.https.yaml` on the recovery start
command as well. Use the override files available in the checked-out release.
