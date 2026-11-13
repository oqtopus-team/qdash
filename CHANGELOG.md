# Changelog

QDash release notes cover changes to calibration workflows, deployments, and daily use.

## 1.10.0

QDash 1.10.0 introduces explicit task calls, project-shared calibration state, and a Pi-based
AI runtime. It also improves execution planning, result inspection, and parameter provenance.

> [!IMPORTANT]
> Before deployment, migrate saved Python flows to `TaskCall` (they are not rewritten
> automatically), configure the new model endpoints if you use AI, and pin `MONGO_VERSION`
> in `.env` to the MongoDB version already running. Back up existing data before deployment.

### Breaking changes and upgrade requirements

#### Workflow authoring

Replace task-name strings with `TaskCall` objects, give repeated calls distinct `call_id` values,
and move task parameters and failure handling into each call. Rename one-qubit `mode` to
`execution_mode` and use the new execution-mode names. Replace `SetCRSchedule` with explicit
rounds or directed coupling targets. Remove legacy session options, including
`persist_output_parameters`; control calibration writes per call instead.

Back up saved flows, update them, and test on the Fake backend before hardware use. Pipeline
specifications now use version 2; new version 1 submissions return a converted specification
for resubmission. See [saved-flow migration](docs/developer-guide/workflow/task-calls.md#migrate-saved-flows)
for the complete replacements.

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

Manually pin the existing MongoDB server version once before deployment. `MONGO_VERSION` is
required; the example value for new installations is not an upgrade instruction.
QDash deployment does not upgrade the MongoDB server or its feature compatibility version.
See [MongoDB pinning](docs/user-guide/mongodb-upgrade.md#check-and-pin-the-running-release).

Application data migrates automatically: `task deploy` and `task deploy-local` run the Compose
`calibration-migration` service, and the API, deployment service, and worker wait for success.
User-owned calibration state, indexes, and artifact paths become project-scoped; duplicate
records are consolidated and displaced records archived. Back up databases, artifacts,
configuration, and saved flows first. If migration fails, inspect its logs, fix the cause,
and retry deployment. An older checkout does not reverse stored-data changes; recovery requires
backups. Follow [System Updates](docs/user-guide/system-updates.md) for the routine upgrade.

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
