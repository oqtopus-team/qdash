# 1-Qubit Calibration Scheduler

`OneQubitScheduler` turns qubit or MUX targets into an execution order that respects wiring-box,
MUX, and shared-module constraints.

## Wiring Model

Each wiring entry names a MUX and its control, read-in, read-out, and pump modules. Module IDs whose
base name ends in `A` or `B` determine the box classification of that MUX.

| Classification | Meaning | Scheduling consequence |
| --- | --- | --- |
| `A` | All recognized modules belong to Box A | Run in the A stage |
| `B` | All recognized modules belong to Box B | Run in the B stage |
| `MIXED` | Modules span both boxes, are unrecognized, or mapping is missing | Isolate from A and B stages |

Qubit-to-MUX mapping follows the hardware convention that MUX `N` owns qubits `4N` through
`4N + 3`. Within a stage, different MUX groups may run in parallel, while qubits in the same MUX
group run sequentially.

MIXED MUXes need one additional constraint. MUXes that use the same Box B control-module base ID
are placed in different sequential groups.

```mermaid
flowchart LR
    targets[Qubit or MUX targets] --> wiring[Classify from wiring]
    wiring --> a[Box A stage]
    wiring --> b[Box B stage]
    wiring --> mixed[MIXED MUXes]
    mixed --> shared[Separate shared Box B modules]
    shared --> mixedStages[One or more MIXED stages]
    a --> order[Execution order]
    b --> order
    mixedStages --> order
```

The result executes A, B, and then every MIXED stage. MUX groups inside one stage are parallel;
the qubits inside each group remain sequential.

## Schedule Forms

The scheduler exposes three forms for different execution APIs.

| Method | Result | Use when |
| --- | --- | --- |
| `generate()` | `OneQubitScheduleResult` | Each MUX worker runs its qubits sequentially |
| `generate_synchronized()` | `SynchronizedOneQubitScheduleResult` | All MUXes must finish position N before position N+1 starts |
| `generate_simultaneous_spectroscopy_batches()` | `MuxBatchScheduleResult` | One spectroscopy call measures a whole selected batch |

Each form has a corresponding `*_from_mux()` convenience method that expands MUX IDs and applies
`exclude_qids` before scheduling.

### MUX-group schedule

```python
from qdash.workflow.engine import OneQubitScheduler

scheduler = OneQubitScheduler(chip_id="64Qv3")
schedule = scheduler.generate_from_mux(
    mux_ids=[0, 1, 2],
    exclude_qids=["5"],
)

for stage in schedule.stages:
    run_mux_groups_in_parallel(stage.parallel_groups)
```

Stages are ordered A, B, then MIXED. Multiple MIXED stages can appear when shared Box B modules
force sequential groups. `parallel_groups` is grouped by MUX and sorted by MUX ID.

### Synchronized schedule

`generate_synchronized()` emits a flat list of steps, which the `parallel_by_round` execution mode
runs as rounds. Box stages remain sequential, and every `parallel_qids` list is one round: each of
its qubits runs the step's full call list, and the next round starts when all of them finish. Checkerboard ordering is enabled by default;
the exact ordering policy is described in
[1-Qubit Ordering Strategies](./one-qubit-ordering-strategies.md).

### Simultaneous spectroscopy schedule

The spectroscopy API accepts `mode="local_index"` or `mode="all"`.

- `local_index` creates up to four steps based on `int(qid) % 4`.
- `all` creates one step containing all selected qubits.

This API reports box classification for observability but does not split the batch on A/B resource
conflicts. Its caller and backend operation must support the selected simultaneous measurement.

## Invariants and Failure Behavior

- An empty qubit or MUX selection raises `ValueError`; excluding every expanded qubit does too.
- A missing wiring file raises `FileNotFoundError`.
- An unmapped qubit is classified as MIXED conservatively.
- Stage and MUX order are deterministic.
- A result describes legal ordering only. It does not acquire a hardware reservation or execute a
  backend call.

## Execution Modes

A one-qubit step's `execution_mode` selects a strategy in `ONE_QUBIT_STRATEGIES`
(`workflow/service/strategy.py`), and the strategy selects a schedule form. Every strategy except
`simultaneous_spectroscopy` runs a target's full call list as one unit of work, so a mode decides
only when targets wait for each other.

| `execution_mode` | Former name | Strategy | Schedule form | Waiting rule |
| --- | --- | --- | --- | --- |
| `parallel_by_mux` | `scheduled` | `OneQubitScheduledStrategy` | MUX-group | Each MUX group starts its next qubit when its current qubit finishes |
| `parallel_by_round` | `synchronized` | `OneQubitSynchronizedStrategy` | Synchronized | A round of qubits from different MUXes finishes before the next round starts |
| `sequential` | `serial` | `OneQubitSerialStrategy` | MUX-group | One qubit at a time, MUX group after MUX group |
| `simultaneous_spectroscopy` | — | `OneQubitSimultaneousSpectroscopyStrategy` | Simultaneous spectroscopy | Each call is a barrier for its batch |

A round is the set of qubits the scheduler places in one synchronized step. It is not a per-task
barrier and does not align pulse timing. With MUX 0 holding qubits 0 and 1 and MUX 1 holding
qubits 4 and 5, `parallel_by_mux` can start qubit 1 while qubit 4 is still running, and
`parallel_by_round` finishes qubits 0 and 4 before qubits 1 and 5 start. The actual grouping and
order come from the schedule. The three non-spectroscopy strategies keep box stages sequential and
delegate parallel worker creation to the service scheduling helpers.

`BringUp` and the flow templates that take an `execution_mode` parameter default to
`parallel_by_mux`; `OneQubitCheck`,
`OneQubitFineTune`, `CustomOneQubit`, and the pipeline spec default to `parallel_by_round`.
`normalize_one_qubit_execution_mode()` in `datamodel/one_qubit_execution_mode.py` is the single
place that maps the deprecated `mode` argument and the former names to the canonical mode. Each
entry point treats an omitted value as `None`, so its own default never conflicts with an
explicit legacy `mode`; explicit values that name different modes raise `ValueError`. Step
classes and templates emit a `DeprecationWarning` and repeat it in the run log, and the pipeline
spec reports it through validation warnings. The stage result keys (`1q_scheduled`,
`1q_synchronized`, `1q_serial`) and the scheduler method names keep their former names.

## Source and Tests

- `workflow/engine/scheduler/one_qubit_scheduler.py` owns wiring classification and schedule
  generation.
- `workflow/engine/scheduler/one_qubit_types.py` defines the three result forms.
- `workflow/engine/scheduler/one_qubit_plugins.py` defines ordering strategies.
- `workflow/service/strategy.py` maps execution modes to strategies that consume schedules.
- `datamodel/one_qubit_execution_mode.py` defines the execution modes and their deprecated aliases.
- `tests/qdash/workflow/engine/scheduler/test_one_qubit_scheduler.py` covers classification,
  grouping, synchronized steps, and spectroscopy modes.

`tests/qdash/workflow/service/test_one_qubit_execution_mode.py` and
`tests/qdash/datamodel/test_one_qubit_execution_mode.py` cover the execution modes, their defaults,
and the deprecated aliases.

Run the scheduler test module after scheduler changes. Update the ordering tests as well when a change affects
the order within a MUX or across synchronized steps.
