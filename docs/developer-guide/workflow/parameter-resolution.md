# Parameter Resolution

Tasks resolve calibration inputs, experiment settings, and output publication separately.

## Parameter model contracts

| Declaration | Runtime values | Purpose |
| --- | --- | --- |
| `input_spec` | `input_parameters` | Calibration inputs and override rules |
| `run_spec` | `run_parameters` | Experiment configuration |
| `output_spec` | `output_parameters` | Measured outputs and publication targets |

Specs are immutable; each task instance creates its own runtime models. History records the
effective input and run values.

## Task settings and precedence

[Task Calls](./task-calls.md#settings) set `run`, `input`, and `update_calibration_parameters`.
Run values resolve from highest priority to lowest:

1. Call settings.
2. Internal per-task defaults from pipeline or single-task requests.
3. Legacy per-task entries in `default_run_parameters`.
4. Shared `default_run_parameters`.
5. Task `run_spec` defaults.

Only declared run names receive shared defaults. Unknown or misplaced call settings fail rather
than being ignored. Sweeps accept `sweep.linspace`, `logspace`, `arange`, `range`, and `values`;
scalar parameters still require scalars.

Qubex's `readout_duration` is session-scoped: set it in shared defaults (1024 ns when omitted).
A per-call value must agree. Spectroscopy uses its own pulse durations and does not expose this
shared setting.

Preprocessing resolves declared inputs from the database or allowed defaults, then the executor
applies permitted explicit overrides. A required database input must exist even when an override
is supplied. Forbidden overrides and batch input overrides are rejected.

## Execution-level parameter policy

| Operation | Baseline | Write-back default |
| --- | --- | --- |
| Normal workflow | Current calibration and task/workflow settings | On |
| Tasks quick run | Current calibration and submitted settings | Off |
| Snapshot re-execution API | Recorded input and run values | On for single-task re-execution |

The UI's **Run again** uses a quick run prefilled with compatible historical values; it is not
snapshot restoration. **Reload** fills fields from current values, and submitted non-empty
fields are explicit overrides.

## Snapshot re-execution

`source_task_id` selects one exact result. A `source_execution_id` lookup matches task, target,
step ID, and call ID. Ambiguous legacy results fail instead of selecting arbitrarily.
Snapshots and their exemptions propagate to every step and isolated worker.

The executor restores recorded input and run collections, merges explicit overrides, and marks
inputs resolved so preprocessing cannot reload current calibration. Missing required snapshot
inputs fail; there is no silent fallback to today's database or YAML.

### Effective-input validation

Validate numeric constraints after resolution and overrides, before measurement. Tasks must not
repair invalid effective inputs or mutate input/run collections. Only a missing value with an
explicit `database_or_default` policy may use its declared fallback.

### Single-task result re-execution

`POST /task-results/{task_id}/re-execute` restores the exact snapshot and accepts
`parameter_overrides` with `input` and `run` entries. These affect the requested task, not an
optional preceding Configure task. `POST /tasks/{task_name}/execute` starts a quick run instead;
its optional source task ID records provenance only.

## Output persistence

Write-back resolves from the call's `update_calibration_parameters`, then its per-task default,
then `True`. False retains history and artifacts but skips accepted calibration and engine-owned
backend parameter writes. Task-specific hardware side effects can still occur; see
[Cross-Resonance Tasks](./cross-resonance-tasks.md).

Single-task execution uses a top-level `update_calibration_parameters` for the requested task
and optional Configure call. False also disables GitHub push. Agent actions send false.
Deprecated `persist_output_parameters` or nested settings are accepted only when all supplied
values agree; conflicts fail before hardware work. Migrate to the top-level field.

`force_update_params` (API `update_params`) does not enable publication by itself. Publication
must be enabled before forced backend updates can occur.
For destinations and failure ordering, see [Calibration Data Lifecycle](./calibration-data-lifecycle.md).

## Implementation files

- `src/qdash/workflow/calibtasks/base.py` and `calibtasks/qubex/base.py`
- `src/qdash/workflow/engine/task_parameters.py`
- `src/qdash/workflow/engine/task/snapshot_loader.py`, `executor.py`, and `backend_saver.py`
- `src/qdash/workflow/service/_internal/settings.py`
- `src/qdash/workflow/service/single_task_flow.py`

Run `task test-workflow` when changing resolution, snapshots, or publication.
