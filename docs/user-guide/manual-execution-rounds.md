# Write Manual Execution Rounds

Set `execution_mode="manual"` on a calibration step to choose its rounds yourself: you list which
qubits, or which directed coupling pairs, run together and in what order, and QDash runs exactly
that list. Use it when a procedure needs a specific grouping that the automatic modes in
[Creating Workflows](./creating-workflows.md#choose-an-execution-mode) do not produce.

A round is a set of targets that run in parallel. Every target of a round runs the step's whole
task list, and the next round starts only after every target of the current round has finished.
Rounds run in the order you write them, and the targets of a round are submitted in the order you write
them. QDash never regroups, reorders, splits or reverses manual rounds, and it does not
synchronize pulses or tasks between the targets of a round: a round is the same waiting rule as
`parallel_by_round`, with your grouping instead of the scheduler's.

| Execution mode | Who forms the rounds or groups | Where to read more |
| --- | --- | --- |
| `parallel_by_round` (one-qubit default) | The scheduler, from the chip wiring, when the run starts | [Choose an Execution Mode](./creating-workflows.md#choose-an-execution-mode) |
| `automatic` (two-qubit default) | The CR scheduler, or an earlier `GenerateCRSchedule` or `SetCRSchedule` step | [Schedule Two-Qubit Calibration](./creating-workflows.md#schedule-two-qubit-calibration) |
| `manual` | You, in the `rounds` of the step | This page |

## Write One-Qubit Rounds

`CustomOneQubit`, `OneQubitCheck`, and `OneQubitFineTune` accept `execution_mode="manual"` with
`rounds`, a list of rounds that each list qubit IDs as strings without leading zeros, such as
`"7"`:

```python
from prefect import flow

from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets


@flow
def rabi_in_rounds(username: str, chip_id: str, project_id: str | None = None,
                   flow_name: str | None = None):
    cal = CalibService(username, chip_id, project_id=project_id, flow_name=flow_name)
    steps = [
        CustomOneQubit(
            step_name="rabi_rounds",
            execution_mode="manual",
            rounds=[["0", "8"], ["1", "9"]],
            tasks=[TaskCall(name="CheckRabi"), TaskCall(name="CheckT1")],
        ),
    ]
    return cal.run(QubitTargets(["0", "8", "1", "9"]), steps=steps)
```

Qubits 0 and 8 run first, each through CheckRabi and then CheckT1; qubits 1 and 9 start after
both qubit 0 and qubit 8 have finished.

The rounds must name exactly the step's current qubits: the targets of the run, without excluded
qubits, after any earlier filter step. A qubit that is in a round but not a current qubit, and a
current qubit that is in no round, both stop the step before it measures; QDash neither drops nor
adds a qubit. In the example, `QubitTargets(["0", "8", "1", "9"])` matches the rounds;
`MuxTargets([0, 2])` would also select qubits 2, 3, 10, and 11 and fail. `OneQubitCheck` always
compares its rounds with the run's targets, as it does in the other modes.

QDash checks one-qubit rounds against the chip's topology and wiring with the rules the automatic
round schedule follows. The MUX of each qubit comes from the chip's topology template, as for
every other run; a chip without a topology keeps MUX `N` = qubits `4N` to `4N + 3`.

- a qubit appears in only one round of a step, because its result would otherwise be overwritten;
- every qubit is defined by the chip's topology, and a qubit in a MUX has a MUX entry in the chip
  wiring;
- a standalone qubit, which the topology lists in no MUX, runs alone in its round, because QDash
  does not know which hardware it shares;
- the qubits of one round use different MUXes;
- a round does not mix Box A, Box B, and mixed MUXes, which the scheduler runs in separate stages;
- mixed MUXes of one round do not share a Box B control module.

## Write Two-Qubit Rounds

`CustomTwoQubit` and `TwoQubitCalibration` take `execution_mode="automatic"` by default and
accept `execution_mode="manual"` with `rounds` of directed `(control, target)` pairs:

```python
from qdash.workflow import TaskCall
from qdash.workflow.service.steps import CustomTwoQubit

CustomTwoQubit(
    step_name="cr_rounds",
    execution_mode="manual",
    rounds=[[("0", "1"), ("4", "5")], [("8", "9")]],
    tasks=[TaskCall(name="CheckCrossResonance")],
)
```

Pairs 0 → 1 and 4 → 5 run together; pair 8 → 9 starts after both have finished. QDash checks
that:

- every pair is a coupling of the chip in exactly the written direction; `("5", "4")` is a
  different pair from `("4", "5")`, and QDash never reverses it;
- both qubits of every pair are among the step's current qubits and are defined by the chip's
  topology;
- the pairs of one round share no qubit, no MUX, and no MUX whose readout or control module is
  shared in the chip wiring;
- a pair with a standalone qubit runs alone in its round;
- a directed pair appears in only one round of a step.

A manual two-qubit step ignores a CR schedule from an earlier `GenerateCRSchedule` or
`SetCRSchedule` step. `max_parallel_ops` caps only automatic groups, so a manual step that sets
it is rejected; split a round yourself to run fewer pairs at once. `SetCRSchedule` still runs its
hand-written groups without any of these checks; prefer a manual step when you want the groups
checked before the run.

A step without `execution_mode="manual"` that sets `rounds`, a manual step without `rounds`, and
an unknown `execution_mode` all fail when the workflow builds its steps. The same `execution_mode`
and `rounds` fields work in calibration pipeline specs, where pairs are written as lists:
`[[["0", "1"], ["4", "5"]], [["8", "9"]]]`.

## Review the Execution Preview

1. Save the workflow; a run always executes the saved version.
2. Select **Execute**, then the **Execution preview** tab.
3. Read each step: manual steps show **Manual rounds · user-defined** with a table of their rounds,
   tasks, and any problems; automatic steps show **Automatic · formed at run time** and no
   rounds, because the scheduler forms them when the run starts.
4. Fix any listed problem in the source and save. While manual rounds have a problem,
   **Execute** stays disabled.

**Play round order** highlights the rounds one after another to show their order; it shows no
durations. The illustration under the steps is an example with other qubits and is labelled as
not this run.

The preview reads the source without running it. When the steps depend on values only known at
run time, such as a condition on a runtime value, a loop, or a helper function, the preview says
it cannot resolve the steps and shows no partial plan; you can still execute, and QDash checks
manual rounds again before any qubit or pair is measured. The same applies when a `return` that
depends on a runtime value comes before a `cal.run(...)` call, and when the saved parameters
reach a `raise`. A check that raises an error on a runtime value, such as
`if not qids: raise ValueError(...)`, does not affect the preview: it stops a failing run, and a
run that passes it runs the steps shown. Unsaved editor changes are not part of the preview or the
run. The preview shows planned steps assuming runtime checks pass; a failed check can stop
execution. Preview and execution are not locked to the same saved-source version: another save
between them can change the source that executes.

## What the Checks Cover

A round tells QDash which targets may run in parallel, not that they measure at the same moment.
Each parallel executor has 16 worker slots; resource availability and deployment settings can
reduce actual concurrency. Targets beyond those slots wait for earlier targets to finish, still
before the next round. The checks use the chip's topology, wiring, and coupling list that QDash
models; when the topology of the chip cannot be loaded, the preview and the run reject every
round. The checks do not prove that your hardware can drive every target of a round together. On wiring written as `<box ID>:<port>`, such as QuEL-3, every MUX is a mixed MUX and
QDash can only check shared MUXes and, for pairs, shared modules; see
[Check Parallel Execution on QuEL-3](./setup/qubex-backend.md#check-parallel-execution-on-quel-3).

The targets of a manual workflow come from its rounds, so **Execute** offers no target override
for it, and a run with an override is rejected.

How this works: [1-Qubit Calibration Scheduler](../developer-guide/architecture/one-qubit-scheduler.md#manual-rounds)
and [CR Gate Scheduler](../developer-guide/architecture/cr-scheduler.md#manual-rounds).
