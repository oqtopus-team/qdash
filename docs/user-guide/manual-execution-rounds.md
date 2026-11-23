# Write Manual Execution Rounds

Use `execution_mode="manual"` when you need exact target groups and order. Each target runs its
whole task list; the next round waits for all targets in the current round.
Start with [Creating Workflows](./creating-workflows.md) to open and save a flow, then replace
its step with the example you need below. Use qubit IDs and couplings from your chip.

## Write One-Qubit Rounds

`CustomOneQubit`, `OneQubitCheck`, and `OneQubitFineTune` accept rounds of qubit IDs:

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
    steps = [CustomOneQubit(
        step_name="rabi_rounds",
        execution_mode="manual",
        rounds=[["0", "8"], ["1", "9"]],
        tasks=[TaskCall(name="CheckRabi"), TaskCall(name="CheckT1")],
    )]
    return cal.run(QubitTargets(["0", "8", "1", "9"]), steps=steps)
```

The rounds must cover the step's current targets exactly once, after exclusions and filters.
`OneQubitCheck` compares against the run's targets. IDs must exist in the topology and use
canonical strings, such as `"7"` rather than `"07"`.

Within a round, use different MUXes and compatible wiring stages. Mixed MUXes cannot share a
Box B control module. A standalone qubit runs alone. QDash validates these conditions before
measurement; it does not silently repair a round.

## Write Two-Qubit Rounds

Start from **2Q Manual Rounds** and edit `ROUNDS` and `TARGET_PAIRS` together. The step takes
directed `(control, target)` pairs:

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

Each directed pair must exist on the chip, use current targets, and appear only once. Pairs in
a round cannot share qubits, MUXes, or conflicting readout/control modules. A pair containing a
standalone qubit runs alone. Manual steps ignore earlier CR schedules and reject `max_parallel_ops`;
split the rounds yourself.

## Review the Execution Preview

1. Save the workflow and select **Execute → Execution preview**.
2. Check the manual-round table and fix any reported problems.
3. Save again before executing. The run uses saved source, not unsaved edits.

Runtime-dependent source can prevent a preview without blocking execution. QDash validates
manual rounds again before measurement. Manual workflows do not accept target overrides.

## What the Checks Cover

Rounds permit parallel execution, not simultaneous pulses. Executors have 16 worker slots;
additional targets wait within the round. Topology and wiring checks do not prove hardware
capacity. Verify the deployment's [parallel-execution limits](./setup/qubex-backend.md#check-parallel-execution-on-quel-3)
before running on hardware.
