# 1-Qubit Ordering Strategies

Ordering strategies choose qubit order inside a MUX and each MUX's contribution to a round.
The [scheduler](./one-qubit-scheduler.md) still owns hardware stages and conflicts.

## Strategy Contract

`MuxOrderingStrategy` defines three methods:

| Method | Responsibility |
| --- | --- |
| `order_qids_in_mux()` | Order the supplied qubits of one MUX |
| `generate_rounds()` | Cover the supplied qubits exactly once in rounds |
| `get_metadata()` | Identify the ordering policy and its settings |

Use topology member-slot order rather than assuming qubit IDs encode MUX membership.

## Built-in Strategies

`DefaultOrderingStrategy` uses local slot order. `CheckerboardOrderingStrategy` alternates slot
order by MUX parity. Round scheduling uses checkerboard ordering by default; `use_checkerboard`
selects the built-in policy. MUX-group scheduling can accept a custom strategy.

The scheduler applies ordering within A, B, and MIXED stages. A strategy must not merge stages or
introduce qubits that the caller did not select.

## Add a Strategy

Implement all three methods, return stable metadata, and test empty/sparse selections plus exact
coverage without duplicates. Then test its composition with wiring constraints; a correct local
order alone does not establish a valid schedule.

## Source and Tests

- `src/qdash/workflow/engine/scheduler/one_qubit_plugins.py`: contract and built-ins.
- `src/qdash/workflow/engine/scheduler/one_qubit_scheduler.py`: stage composition.

Run both suites from the repository root:

```bash
uv run pytest tests/qdash/workflow/engine/scheduler/test_one_qubit_plugins.py tests/qdash/workflow/engine/scheduler/test_one_qubit_scheduler.py
```
