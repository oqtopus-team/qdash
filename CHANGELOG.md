# Changelog

QDash release notes describe changes that affect calibration workflows, deployments, and daily use.

## 1.10.0

QDash 1.10.0 makes calibration state shared within a project, gives each task call explicit
settings and an identity, and introduces a Pi-based AI runtime for investigation and calibration
assistance. This release also expands workflow scheduling, result inspection, and parameter
provenance. Existing deployments and saved workflows require the updates below.

### Breaking changes and upgrade instructions

#### Rewrite saved calibration flows with explicit task calls

Saved Python workflows are not rewritten automatically. Back up
`src/qdash/workflow/user_flows` before editing, then update and test each flow on the Fake backend
before running it on hardware.

- Replace task-name strings with `TaskCall` objects. Give repeated occurrences of the same task
  distinct `call_id` values so results, filters, and re-execution identify the intended call.
- Move `CalibService(task_parameters=...)` and `task_run_parameters` settings into each call's
  `run`, `input`, and `update_calibration_parameters` fields. Preserve existing per-call overrides.
  Use `default_run_parameters` only for run settings shared across tasks.
- Replace `stop_on_failure_tasks` with `on_failure="stop"` on the relevant calls. This stops the
  remaining calls for that target in the step; it does not stop every target in the workflow.
- Rename one-qubit `mode` to `execution_mode`: `serial` becomes `sequential`, `scheduled` becomes
  `parallel_by_mux`, and `synchronized` becomes `parallel_by_round`. The old names are rejected.
- Replace `SetCRSchedule` with explicit two-qubit `rounds` and `execution_mode="manual"`, or use
  `CouplingTargets` to select directed pairs for automatic grouping. The unchecked setter and
  **2Q Scheduled Calibration** template have been removed.
- Remove session-level `persist_output_parameters`; set `update_calibration_parameters=False`
  on every call that must remain measurement-only, including calls executed in parallel.

For example, replace a task-name list with explicit calls:

```python
from qdash.workflow import TaskCall

tasks = [
    TaskCall(name="Configure", on_failure="stop"),
    TaskCall(name="CheckRamsey", call_id="ramsey_coarse", run={"detuning": 0.001}),
    TaskCall(name="CheckRamsey", call_id="ramsey_fine", run={"detuning": 0.0002}),
    TaskCall(name="CheckT1", update_calibration_parameters=False),
]
```

`CalibService` now exposes a narrower authoring API: pass targets to `cal.run(...)`, and let QDash
manage execution IDs and hardware reservations. Legacy constructor options raise errors with
migration hints. GitHub synchronization follows `github.enabled` and `github.branch` in
`config/app/workflow.yaml`; disabling calibration writes does not disable synchronization.

Pipeline specifications now use version 2. The API rejects new version 1 submissions with a
converted `migrated_spec` to resubmit; the worker converts version 1 specifications already queued.
The old one-qubit `mode` key still requires a manual edit, including in queued specifications.

See [workflow migration](docs/developer-guide/workflow/task-calls.md#migrate-saved-flows),
[workflow authoring](docs/user-guide/creating-workflows.md), and
[pipeline specifications](docs/developer-guide/workflow/calibration-pipeline.md) for the complete
changes, including result access and call-specific filters.

#### Reconfigure AI endpoints for the new runtime

Copilot now uses the Pi-based `agent-runtime` and its `agent-exec` workspace. Both start with the
standard Compose stack, and internal authentication is generated and retained in a Docker volume.
No AI Compose profile or UI enable flag is required. Calibrations can run without AI endpoints.

Review existing model configuration rather than carrying the former shared model and
`review.yaml` configuration forward unchanged:

1. Set `OPENAI_COMPATIBLE_BASE_URL_CHAT` and `OPENAI_COMPATIBLE_API_KEY_CHAT` for chat, and
   `OPENAI_COMPATIBLE_BASE_URL_EVALUATION` and `OPENAI_COMPATIBLE_API_KEY_EVALUATION` for figure
   evaluation in `.env`. Custom endpoint URLs must include `/v1`, without `/chat/completions`
   or `/responses`.
2. Choose models in `config/copilot/chat.yaml` (`chat_models`) and
   `config/copilot/evaluation.yaml` (`evaluation_models`). Use distinct endpoint identifiers,
   such as `openai-compatible-chat` and `openai-compatible-evaluation`, for different base URLs.
3. If endpoints use Cloudflare Access, set both `CF_ACCESS_CLIENT_ID` and
   `CF_ACCESS_CLIENT_SECRET`. Keep any API key the model server itself requires.
4. Recreate the runtime after changing environment values:
   `docker compose up -d --build --force-recreate agent-runtime`.

The optional classifier uses `CLASSIFIER_BASE_URL`, `CLASSIFIER_API_KEY`, and
`config/copilot/classifier.yaml`. Chat works without it. The retired
`AGENT_RUNTIME_ENABLE_WRITE_TOOLS` setting has no effect; writes require approval and project
permissions.

Saved conversations live in `agent-runtime-state`. When upgrading an existing Pi deployment,
back up that volume while the runtime is stopped: a newer Pi release can migrate conversations
that an older release cannot read. See [AI setup](docs/user-guide/setup/ai.md),
[model configuration](docs/developer-guide/copilot/model-configuration.md), and
[system updates](docs/user-guide/system-updates.md).

#### Pin MongoDB before upgrading QDash

`MONGO_VERSION` is now required in `.env`; Compose refuses to run when it is missing or empty.
Before changing the checkout or stopping the existing deployment, read the running MongoDB
version and pin that exact version. Keep the existing environment file. The example value
`MONGO_VERSION=9.0.8` is for a new installation with an empty data directory, not an automatic
upgrade of an existing database.

Installing QDash 1.10.0 does not upgrade the MongoDB server or its feature compatibility version
(FCV). Upgrade the database server separately, with a backup and the intermediate versions
required by its current release and FCV. Follow [Upgrade MongoDB](docs/user-guide/mongodb-upgrade.md)
for discovery, pinning, supported upgrade paths, verification, and recovery.

#### Migrate project calibration data before services resume

The QDash data migration is separate from the MongoDB server upgrade. Calibration state previously
owned by individual users is consolidated by project: members of one project now use the same
chip, qubit, and coupling calibration state. Execution counters and unique indexes become
project-scoped, and calibration artifacts move into the project/date layout with stored paths
updated to match. Duplicate records are consolidated, with displaced records archived before
deletion. Migration completion is recorded so completed work can be skipped on subsequent runs.

Plan a maintenance window and follow this order:

1. Finish or cancel workflows and stop external writers. Record and pin MongoDB as above.
2. Stop QDash and take consistent backups of MongoDB, PostgreSQL, calibration artifacts, Qubex
   configuration, and saved flows. Back up the stopped AI conversation volume if it already exists.
3. Select the release and rebuild using [System Updates](docs/user-guide/system-updates.md).
   Standard Compose starts the `calibration-migration` service, which runs
   `python -m qdash.dbmodel.migration run --execute`. The API, deployment service, and user-flow
   worker wait for that service to succeed.
4. Inspect `docker compose logs calibration-migration` before resuming work. Resolve missing
   project scope or missing calibration artifacts if migration fails; do not bypass the startup
   dependency. Confirm the calibration-data mount points at the existing artifacts.
5. Check project membership, current calibration values, historical results, and figure access,
   then test the migrated workflows on a small target before restoring schedules.

For a migration preview with the new image built and MongoDB available, run
`docker compose run --rm --no-deps calibration-migration python -m qdash.dbmodel.migration run`.
Omitting `--execute` previews data changes; it is not a substitute for a backup or a guarantee of
zero database writes, because migration infrastructure can create indexes.

The runner also applies registered task-history renames for adaptive Chevron tasks and the
candidate-set commit collection. It does not rewrite saved Python workflows or run every legacy
maintenance command in the migration module. Returning to an older checkout does not undo data
or artifact migration; recovery requires the corresponding backups.

#### Distinguish measured results from accepted calibration values

A saved task result no longer implies that its outputs are the current calibration values.
QDash distinguishes task history, accepted calibration values in MongoDB, the active workflow's
state, and the derived Qubex parameter files.

`TaskCall(..., update_calibration_parameters=False)` keeps measurements in history without
replacing accepted values or the inputs of later tasks. Normal workflow calls write back by
default; single-task quick runs default to measurement-only. When validated outputs are applied,
they update the current calibration database and workflow state, and QDash attempts to synchronize
the Qubex parameter files. A file synchronization failure does not roll back the MongoDB update.

Task results show **Calibration DB updated**, **Measurement only**, or **Update status unknown**
for older results without update metadata. Use these labels when deciding whether a measurement
changed the state used by the next task.

Frequency parameters also have explicit roles. `coarse_qubit_frequency` is an exploration
estimate, `qubit_frequency` is a measured device frequency, and `control_frequency` is the drive
setting. Likewise, `resonator_frequency` and `readout_frequency` are distinct. Tasks declare which
accepted values their outputs publish; spectroscopy does not automatically replace every related
frequency. Review custom flows and imports against the
[frequency parameter policy](docs/developer-guide/workflow/frequency-parameter-policy.md).

For manual changes, use **Calibration DB → Modify parameters** to compare YAML candidates with
current values, select and edit permitted parameters, and confirm the import. This is a reviewed
update, not an unconditional replacement of the database from YAML. See
[calibration data and provenance](docs/user-guide/data-and-provenance.md) and the
[calibration data lifecycle](docs/developer-guide/workflow/calibration-data-lifecycle.md).

#### Update direct service connections

The Compose deployment now publishes one entry point through Caddy on `UI_PORT`. Update direct
API clients to `http://<host>:<UI_PORT>/api` and Prefect links to
`http://<host>:<UI_PORT>/prefect`. Database services no longer publish host ports; run database
tools inside their containers. Existing reverse proxies targeting `UI_PORT` can keep that entry
point. See [direct service access](docs/user-guide/system-updates.md#check-direct-service-access)
for proxy settings and conflicting Compose overrides.

### Workflow and hardware highlights

- **Explicit execution plans.** Select directed coupling pairs for automatic scheduling or write
  validated manual rounds for one- and two-qubit work. The workflow editor offers execution help
  and an execution preview before a run. See [manual rounds](docs/user-guide/manual-execution-rounds.md).
- **Per-run targets and organized workflows.** Override targets for an immediate execution without
  changing saved defaults, organize workflows in creator folders, and manage flows from the editor.
- **Expanded calibration tasks.** Adaptive GE, EF, and FH Chevron measurements, EF calibration,
  and GEF relaxation characterization extend device bring-up and higher-level characterization.
  Review each task's configuration prerequisites before adding it to a hardware flow.
- **Hardware-free onboarding.** The Fake backend provides a fixed simulated device for learning
  the application and testing calibration procedures. Start with
  [your first calibration](docs/user-guide/first-calibration.md).

### AI assistance highlights

- **Investigation in context.** AI chat can investigate execution logs and task results, use a
  persistent workspace, and present richer responses and optional structured result layouts.
- **Figure evaluations.** Evaluate calibration plots from the chip view and track evaluation
  progress separately from chat. See [AI evaluations](docs/user-guide/ai-evaluations.md).
- **Agent calibration.** The agent interface supports scoped sessions, action budgets, candidate
  validation, and explicit commits of accepted results. Review the permitted targets and bounds
  before authorizing hardware work. See [agent calibration](docs/user-guide/agent-calibration.md).

### Data review and collaboration highlights

- **Parameter provenance.** Follow **Lineage** from a result, metric history, or execution parameter
  change to its producer, inputs, and derived values; manual edits and seed imports also have provenance.
- **Project-wide calibration.** Shared calibration state, project permissions, and cool-down scope
  provide a common view for laboratory members while retaining execution attribution.
- **Clearer result inspection.** Qubit and coupling views share interactive figure previews, task
  artifact downloads include images, and execution views expose call identities and parameter changes.
- **Daily activity at a glance.** Home shows project execution activity and upcoming workflow runs;
  dashboard and metrics views help inspect coverage and compare calibration results.

The release change set is tracked in [PR #1527](https://github.com/oqtopus-team/qdash/pull/1527).
