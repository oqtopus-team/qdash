# System Updates

Deploy a stable branch or release tag after finishing running calibrations.

## Prepare the Update

Read the target release notes. Back up affected data and preserve `.env`, configuration, and
local source changes. A code rollback does not undo data migrations.

Before the first v1.10.0 update, [pin the running MongoDB release](./mongodb-upgrade.md#check-and-pin-the-running-release).
Upgrade MongoDB separately through its required intermediate releases and FCV steps.
Back up the stopped `agent-runtime-state` volume before a runtime upgrade that migrates conversations.

When upgrading from Copilot naming, move custom `config/copilot/` files to `config/agent/` and
rename `QDASH_COPILOT_PROFILE` to `QDASH_AGENT_PROFILE`. Update clients calling `/copilot/` to
`/agent/`; old routes have no aliases. Saved chats and instructions remain.

## Select a Version

Run from the repository root:

```bash
git fetch origin --tags
git switch main
git pull --ff-only origin main
```

Or select a specific release with `git switch --detach v1.10.0`, replacing the example tag.
Resolve conflicting local changes before deploying.

## Deploy the Release

| Existing deployment | Command |
| --- | --- |
| Compose without bundled tunnel | `task deploy-local` |
| Compose with configured tunnel | `task deploy` |

These also update configured knowledge. Without Go Task, use `docker compose up -d --build`,
retaining your deployment's Compose files and profiles; this does not update knowledge or
add the tunnel profile.

## Verify the Deployment

Run `docker compose ps`, sign in, and check existing data and normal operations.
See [service addresses](./setup.md#verify-the-installation) and [logs](./operations.md#inspect-logs).

## Check Direct Service Access

When migrating from a release without Caddy, use `http://<host>:<UI_PORT>/api` and
`http://<host>:<UI_PORT>/prefect`. Remove overrides publishing `UI_PORT` on `ui`; Caddy now owns
that port. Use [container database shells](./operations.md#open-a-database-shell) for database access.

## Recover from a Failed Update

Follow release-specific recovery instructions before deploying an earlier tag. Restore backups
when required; selecting old source does not reverse stored-data or conversation migrations.
For session-aware releases, follow the [rollback precautions](./operations.md#upgrade-calibration-session-support).
