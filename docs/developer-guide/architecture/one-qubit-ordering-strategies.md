# 1-Qubit Ordering Strategies

Ordering strategies control the order of qubits within each MUX and which qubit position each
MUX contributes to a round of the `parallel_by_round` execution mode. Box classification and
shared-module grouping remain the responsibility of `OneQubitScheduler`.

## Strategy Contract

`MuxOrderingStrategy` defines two operations:

- `order_qids_in_mux()` orders the selected qubits within one MUX for a MUX-group schedule.
- `generate_rounds()` creates chip-wide rounds from a set of MUXes and qubits. A round lists
  qubits from different MUXes that run in parallel; each runs its full task list before the next
  round starts.

Both operations receive `OrderingContext`, which contains the chip ID, qubit-grid size, MUX-grid
size, and qubit-to-MUX map. Strategies return qubit IDs only; they do not inspect wiring resources,
start Prefect tasks, or execute hardware operations.

## Built-in Strategies

`DefaultOrderingStrategy` uses numeric qubit order within each MUX. Its rounds take the same
local offset from every selected MUX:

```text
round 0: 4N
round 1: 4N + 1
round 2: 4N + 2
round 3: 4N + 3
```

`CheckerboardOrderingStrategy` alternates local offsets by MUX parity:

| MUX parity | Offset order |
| --- | --- |
| Even | `0, 1, 2, 3` |
| Odd | `2, 3, 0, 1` |

For MUXes 0 through 3, the rounds are:

```text
round 0: 0, 6, 8, 14
round 1: 1, 7, 9, 15
round 2: 2, 4, 10, 12
round 3: 3, 5, 11, 13
```

This interleaving avoids selecting the same physical row position from every neighboring MUX at
once. It is a scheduling policy based on the fixed four-qubits-per-MUX layout, not a replacement
for measured-frequency validation.

## How the Scheduler Uses a Strategy

For `generate()`, the caller may pass any `MuxOrderingStrategy`. The scheduler applies it
independently to each MUX after box classification.

```python
from qdash.workflow.engine import OneQubitScheduler
from qdash.workflow.engine.scheduler.one_qubit_plugins import (
    CheckerboardOrderingStrategy,
)

scheduler = OneQubitScheduler(chip_id="64Qv3")
schedule = scheduler.generate_from_mux(
    mux_ids=[0, 1, 2, 3],
    ordering_strategy=CheckerboardOrderingStrategy(),
)
```

For `generate_rounds()`, callers select the built-in policy with `use_checkerboard`:
`CheckerboardOrderingStrategy` when true (the default and the `parallel_by_round` strategy's
choice), `DefaultOrderingStrategy` when false. The scheduler creates A rounds, then B rounds, then
one or more MIXED round sequences. Empty local-offset rounds are removed, so a partial target set
can produce fewer than four rounds per sequence.

## Add a Strategy

Subclass `MuxOrderingStrategy` and implement all three abstract methods:

1. Return only qubits supplied to `order_qids_in_mux()`.
2. Return rounds from `generate_rounds()` whose union is exactly the supplied qubit set, without
   duplicates.
3. Return stable metadata that identifies the policy and any parameters that affect ordering.

Keep the strategy deterministic unless nondeterminism is an explicit, tested part of the policy.
Test full and partial MUX selections, even and odd MUX IDs, and the rounds. If the policy
depends on new wiring data, add that responsibility to the scheduler context deliberately rather
than loading files inside the strategy.

## Source and Tests

- `workflow/engine/scheduler/one_qubit_plugins.py` contains the contract and built-ins.
- `workflow/engine/scheduler/one_qubit_scheduler.py` composes strategies with wiring constraints.
- `tests/qdash/workflow/engine/scheduler/test_one_qubit_plugins.py` tests ordering behavior.
- `tests/qdash/workflow/engine/scheduler/test_one_qubit_scheduler.py` tests composition into final
  schedules.

See [1-Qubit Calibration Scheduler](./one-qubit-scheduler.md) for stage semantics and result forms.
