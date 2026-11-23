# Changelog

QDash release notes cover changes to calibration workflows, deployments, and daily use.

## 1.10.0

QDash 1.10.0 introduces explicit task calls, project-shared calibration state, and a Pi-based
AI runtime. It also improves execution planning, result inspection, and parameter provenance.

### Breaking changes and upgrade requirements

#### Workflow authoring

Old flows cannot run unchanged with the new workflow syntax. **After deployment**, either
create a new flow from a [current template](docs/user-guide/creating-workflows.md), or enable
[AI assistance](docs/user-guide/setup/ai.md) and update an existing flow:

1. Open the flow's file on the **Workflow** page.
2. In the AI chat on the right, ask: **“Rewrite this workflow using the latest syntax.”**
3. Review the proposed changes, select **Apply to editor**, and save the flow. Test it on the
   Fake backend before running it on hardware.

The new syntax uses explicit `TaskCall` objects and per-call settings. For manual edits and
pipeline version 2 changes, see [saved-flow migration](docs/developer-guide/workflow/task-calls.md#migrate-saved-flows).

#### AI configuration

Copilot now uses the Pi-based `agent-runtime`, started by the standard Compose stack.
Replace the former shared model and `review.yaml` configuration with
`config/copilot/chat.yaml` and `config/copilot/evaluation.yaml`. Configure the
`OPENAI_COMPATIBLE_BASE_URL_*` and `OPENAI_COMPATIBLE_API_KEY_*` environment variables separately
for `CHAT` and `EVALUATION`; custom base URLs include `/v1`. Calibrations can run without AI.
See [AI setup](docs/user-guide/setup/ai.md) and
[model configuration](docs/developer-guide/copilot/model-configuration.md).

For an existing Pi deployment, back up the stopped `agent-runtime-state` volume before upgrading:
conversation migrations can prevent an older runtime from reading it.

#### MongoDB pinning and automatic calibration migration

> [!IMPORTANT]
> **Before QDash deployment**, set `MONGO_VERSION` in `.env` to the actual MongoDB version
> currently running. **After QDash v1.10.0 deployment**, upgrade MongoDB to 9.0 by following
> the [MongoDB upgrade guide](docs/user-guide/mongodb-upgrade.md), including its required
> intermediate versions and feature compatibility version (FCV) steps. QDash does not upgrade
> MongoDB automatically.

Back up existing data before deployment; see [System Updates](docs/user-guide/system-updates.md).
Calibration data migrates automatically during deployment.

#### Calibration writes and result history

A saved measurement is distinct from an accepted calibration value. Normal workflow calls write
calibration values by default; single-task quick runs default to measurement-only.
Use `update_calibration_parameters=False` to retain results without replacing accepted values
or later tasks' inputs. Accepted updates also attempt Qubex file synchronization; a file-sync
failure does not roll back the database update.

Review result write-status labels and use **Calibration DB → Modify parameters** for reviewed
manual imports. See [data and provenance](docs/user-guide/data-and-provenance.md) and the
[frequency parameter policy](docs/developer-guide/workflow/frequency-parameter-policy.md)
when updating custom flows.

- **Service access:** Caddy now publishes the shared `UI_PORT` entry point; direct API and Prefect
  connections use `/api` and `/prefect`, and databases no longer publish host ports.
  See [direct service access](docs/user-guide/system-updates.md#check-direct-service-access).

### Workflow highlights

- Plan directed coupling targets or validated manual rounds, and preview execution before running.
  See [manual rounds](docs/user-guide/manual-execution-rounds.md).
- Override targets per run, organize saved workflows, and explore expanded Chevron and EF/GEF tasks.
- Test workflows without hardware using the [Fake backend](docs/user-guide/first-calibration.md).

### AI highlights

- Investigate execution logs and results with contextual chat and a persistent workspace.
- Evaluate plots from the chip view with separate [evaluation progress](docs/user-guide/ai-evaluations.md).
- Use [agent calibration](docs/user-guide/agent-calibration.md) with scoped targets, action budgets,
  candidate validation, and explicit commits of accepted results.

### Data and collaboration highlights

- Share project calibration state while retaining execution attribution and project permissions.
- Follow parameter **Lineage** and inspect call identities, parameter changes, and figure previews.
- Review project activity, upcoming runs, and calibration coverage from Home and dashboards.

The release change set is tracked in [PR #1527](https://github.com/oqtopus-team/qdash/pull/1527).
