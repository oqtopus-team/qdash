# Calibration Data Lifecycle

A measured output becomes a later task's input only when it is accepted and published.

## The four places called parameters

| Store | Meaning |
| --- | --- |
| Task-result history | What a task measured |
| MongoDB `qubit.data` or `coupling.data` | Accepted current calibration |
| Workflow `CalibDataModel` | Active workflow state |
| Qubex parameter files | Derived hardware configuration |

## Output outcomes

| Output | History | Current calibration and workflow state | Qubex export |
| --- | --- | --- | --- |
| Validated and applied | Recorded | Updated | Attempted |
| Validated, measurement-only | Recorded | Unchanged | Unchanged by publication |
| Rejected | Diagnostics retained, rejected outputs cleared | Unchanged | Unchanged by publication |

`database_updated` describes the current MongoDB value, not history persistence or file export.
Missing metadata on older results means the update status is unknown. MongoDB is written before
Qubex synchronization; a synchronization failure does not roll it back.

## Coherence Check example

If CheckChevron measures 5.010 GHz while the accepted frequency is 5.000 GHz, a measurement-only
call records 5.010 GHz but later tasks still use 5.000 GHz. An applied call makes 5.010 GHz
available both in this workflow and in future executions.

## Persistence controls

`update_calibration_parameters` resolves per call: explicit call setting, per-task default,
then true. Workflows therefore publish by default; Tasks quick runs default to false.
This policy changes destinations, not input resolution. See
[Parameter Resolution](./parameter-resolution.md#output-persistence).

## Implementation files

- `src/qdash/workflow/engine/task/backend_saver.py`: publication
- `src/qdash/workflow/engine/task/history_recorder.py`: history
- `src/qdash/workflow/engine/task/executor.py`: validation and lifecycle
- `src/qdash/workflow/engine/params_updater.py`: exported parameters

Use `task test-workflow` to verify accepted, measurement-only, rejected, and partial-failure paths.
