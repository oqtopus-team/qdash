# 1-Qubit Ordering Plugins

This document describes the ordering plugin system for the 1-qubit calibration scheduler. Ordering plugins control the execution order of qubits within each MUX during parallel calibration.

## Overview

### Problem

When calibrating multiple qubits in parallel across different MUXes, adjacent qubits (which have similar frequencies) can interfere with each other. The default sequential order `[0, 1, 2, 3]` within each MUX doesn't account for this frequency proximity issue.

### Solution

Ordering plugins allow customizing the qubit execution order within each MUX to minimize frequency interference between simultaneously calibrated qubits across the chip.

## Physical Layout

### 64-Qubit Chip (8×8 Grid)

Each MUX controls 4 qubits in a 2×2 arrangement:

```
MUX internal layout:
┌──────┬──────┐
│ 4N   │ 4N+1 │
├──────┼──────┤
│ 4N+2 │ 4N+3 │
└──────┴──────┘
```

Full chip layout (16 MUXes in 4×4 grid):

```
  0   1 |  4   5 |  8   9 | 12  13
  2   3 |  6   7 | 10  11 | 14  15
  ------+--------+--------+-------
 16  17 | 20  21 | 24  25 | 28  29
 18  19 | 22  23 | 26  27 | 30  31
  ------+--------+--------+-------
 32  33 | 36  37 | 40  41 | 44  45
 34  35 | 38  39 | 42  43 | 46  47
  ------+--------+--------+-------
 48  49 | 52  53 | 56  57 | 60  61
 50  51 | 54  55 | 58  59 | 62  63
```

### Frequency Pattern

Adjacent qubits have similar frequencies due to the chip design:

```
Frequency distribution (approximate MHz):
8060  8960 | 8200  9100 | 8060  8960 | 8200  9100
8890  7990 | 9030  8130 | 8890  7990 | 9030  8130
-----------+-----------+-----------+-----------
8200  9100 | 8060  8960 | 8200  9100 | 8060  8960
9030  8130 | 8890  7990 | 9030  8130 | 8890  7990
...
```

## Available Plugins

### DefaultOrderingStrategy

Uses natural qubit ID order within each MUX.

```python
from qdash.workflow.engine.calibration import (
    OneQubitScheduler,
    DefaultOrderingStrategy,
)

scheduler = OneQubitScheduler(chip_id="64Qv3")
schedule = scheduler.generate_from_mux(
    mux_ids=list(range(16)),
    ordering_strategy=DefaultOrderingStrategy(),  # Same as no strategy
)
```

**Order pattern:**

- All MUXes: `[0, 1, 2, 3]` offset order

**Example:**

- MUX 0: `[0, 1, 2, 3]`
- MUX 1: `[4, 5, 6, 7]`

### CheckerboardOrderingStrategy

Creates a checkerboard pattern across the chip where simultaneously calibrated qubits are spatially and frequency-separated.

```python
from qdash.workflow.engine.calibration import (
    OneQubitScheduler,
    CheckerboardOrderingStrategy,
)

scheduler = OneQubitScheduler(chip_id="64Qv3")
schedule = scheduler.generate_from_mux(
    mux_ids=list(range(16)),
    ordering_strategy=CheckerboardOrderingStrategy(),
)
```

**Order pattern:**

- Even MUXes (0, 2, 4, ...): `[0, 1, 2, 3]` offset order
- Odd MUXes (1, 3, 5, ...): `[2, 3, 0, 1]` offset order

**Example:**

- MUX 0 (even): `[0, 1, 2, 3]`
- MUX 1 (odd): `[6, 7, 4, 5]`
- MUX 2 (even): `[8, 9, 10, 11]`
- MUX 3 (odd): `[14, 15, 12, 13]`

## Checkerboard Pattern Visualization

### Step-by-Step Execution

When using `CheckerboardOrderingStrategy`, the 4 calibration steps execute qubits in a checkerboard pattern:

```
=== Step 1: [0,6,8,14,16,22,24,30,32,38,40,46,48,54,56,62] ===
  X   . |  .   . |  X   . |  .   .
  .   . |  X   . |  .   . |  X   .
  ------+--------+--------+-------
  X   . |  .   . |  X   . |  .   .
  .   . |  X   . |  .   . |  X   .
  ------+--------+--------+-------
  X   . |  .   . |  X   . |  .   .
  .   . |  X   . |  .   . |  X   .
  ------+--------+--------+-------
  X   . |  .   . |  X   . |  .   .
  .   . |  X   . |  .   . |  X   .

=== Step 2: [1,7,9,15,17,23,25,31,33,39,41,47,49,55,57,63] ===
  .   X |  .   . |  .   X |  .   .
  .   . |  .   X |  .   . |  .   X
  ------+--------+--------+-------
  .   X |  .   . |  .   X |  .   .
  .   . |  .   X |  .   . |  .   X
  ------+--------+--------+-------
  .   X |  .   . |  .   X |  .   .
  .   . |  .   X |  .   . |  .   X
  ------+--------+--------+-------
  .   X |  .   . |  .   X |  .   .
  .   . |  .   X |  .   . |  .   X

=== Step 3: [2,4,10,12,18,20,26,28,34,36,42,44,50,52,58,60] ===
  .   . |  X   . |  .   . |  X   .
  X   . |  .   . |  X   . |  .   .
  ------+--------+--------+-------
  .   . |  X   . |  .   . |  X   .
  X   . |  .   . |  X   . |  .   .
  ------+--------+--------+-------
  .   . |  X   . |  .   . |  X   .
  X   . |  .   . |  X   . |  .   .
  ------+--------+--------+-------
  .   . |  X   . |  .   . |  X   .
  X   . |  .   . |  X   . |  .   .

=== Step 4: [3,5,11,13,19,21,27,29,35,37,43,45,51,53,59,61] ===
  .   . |  .   X |  .   . |  .   X
  .   X |  .   . |  .   X |  .   .
  ------+--------+--------+-------
  .   . |  .   X |  .   . |  .   X
  .   X |  .   . |  .   X |  .   .
  ------+--------+--------+-------
  .   . |  .   X |  .   . |  .   X
  .   X |  .   . |  .   X |  .   .
  ------+--------+--------+-------
  .   . |  .   X |  .   . |  .   X
  .   X |  .   . |  .   X |  .   .

X = Calibrating, . = Idle
```

### Benefits

1. **Frequency Isolation**: Simultaneously calibrated qubits are never adjacent, ensuring maximum frequency separation
2. **Reduced Crosstalk**: The checkerboard pattern minimizes electromagnetic interference between active qubits
3. **Consistent Pattern**: The same pattern applies across all MUXes for predictable behavior

## Usage Examples

### Basic Usage

```python
from qdash.workflow.engine.calibration import (
    OneQubitScheduler,
    CheckerboardOrderingStrategy,
)

scheduler = OneQubitScheduler(chip_id="64Qv3")

# Generate schedule with frequency-aware ordering
schedule = scheduler.generate_from_mux(
    mux_ids=list(range(16)),  # All 16 MUXes
    ordering_strategy=CheckerboardOrderingStrategy(),
)

# Access parallel groups (ordered by strategy)
for stage in schedule.stages:
    print(f"Stage {stage.box_type}:")
    for group in stage.parallel_groups:
        print(f"  MUX group: {group}")
```

### Integration with Calibration Flow

```python
from prefect import flow, task
from qdash.workflow.engine.calibration import (
    OneQubitScheduler,
    CheckerboardOrderingStrategy,
)
from qdash.workflow.flow import init_calibration, get_session, finish_calibration

@task
def calibrate_mux_qubits(qids: list[str], tasks: list[str]) -> dict:
    """Execute tasks for qubits in a single MUX sequentially."""
    session = get_session()
    results = {}
    for qid in qids:
        results[qid] = {}
        for task_name in tasks:
            results[qid][task_name] = session.execute_task(task_name, qid)
    return results

@flow
def frequency_aware_calibration(username: str, chip_id: str):
    """Calibration with frequency-aware qubit ordering."""
    scheduler = OneQubitScheduler(
        chip_id=chip_id,
        wiring_config_path=f"/app/config/qubex/{chip_id}/config/wiring.yaml",
    )

    # Generate schedule with checkerboard ordering
    schedule = scheduler.generate_from_mux(
        mux_ids=list(range(16)),
        ordering_strategy=CheckerboardOrderingStrategy(),
    )

    tasks = ["CheckRabi", "CheckT1", "CheckT2Echo"]

    for stage in schedule.stages:
        init_calibration(username, chip_id, stage.qids)

        # Execute MUX groups in parallel
        # Qubits within each group run sequentially (in checkerboard order)
        futures = [
            calibrate_mux_qubits.submit(group, tasks)
            for group in stage.parallel_groups
        ]
        results = [f.result() for f in futures]

        finish_calibration()
```

## Creating Custom Ordering Strategies

You can create custom ordering strategies by extending `MuxOrderingStrategy`:

```python
from qdash.workflow.engine.calibration.scheduler.one_qubit_plugins import (
    MuxOrderingStrategy,
    OrderingContext,
)

class ReverseOrderingStrategy(MuxOrderingStrategy):
    """Order qubits in reverse order within each MUX."""

    def order_qids_in_mux(
        self,
        mux_id: int,
        qids: list[str],
        context: OrderingContext,
    ) -> list[str]:
        """Return qubits in reverse order."""
        return sorted(qids, key=lambda x: int(x), reverse=True)

    def get_metadata(self) -> dict:
        return {
            "strategy_name": "reverse",
            "description": "Reverse qubit ID order",
        }

# Usage
scheduler = OneQubitScheduler(chip_id="64Qv3")
schedule = scheduler.generate_from_mux(
    mux_ids=[0, 1],
    ordering_strategy=ReverseOrderingStrategy(),
)
```

## API Reference

### MuxOrderingStrategy (Abstract Base Class)

```python
class MuxOrderingStrategy(ABC):
    @abstractmethod
    def order_qids_in_mux(
        self,
        mux_id: int,
        qids: list[str],
        context: OrderingContext,
    ) -> list[str]:
        """Order qubits within a single MUX."""
        pass

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata."""
        pass
```

### OrderingContext

```python
@dataclass
class OrderingContext:
    chip_id: str           # e.g., "64Qv3"
    grid_size: int         # 8 for 64Q, 12 for 144Q
    mux_grid_size: int     # 4 for 64Q, 6 for 144Q
    qid_to_mux: dict[str, int]  # Qubit ID to MUX ID mapping
```

## Synchronized Scheduling

### Problem with Parallel Groups

The original `generate()` and `generate_from_mux()` methods return `parallel_groups` where each MUX executes its qubits independently. This can lead to timing misalignment between MUXes:

```
Original (parallel_groups):
MUX 0: [0, 1, 2, 3] executes sequentially
MUX 1: [6, 7, 4, 5] executes sequentially
→ No guarantee that MUX 0's step 1 aligns with MUX 1's step 1
```

### Solution: Synchronized Steps

The `generate_synchronized()` method creates step-based scheduling where **all MUXes execute the same step simultaneously**:

```
Synchronized steps (with checkerboard):
Step 0: [0, 6, 8, 14, ...] - 16 qubits simultaneously
Step 1: [1, 7, 9, 15, ...] - 16 qubits simultaneously
Step 2: [2, 4, 10, 12, ...] - 16 qubits simultaneously
Step 3: [3, 5, 11, 13, ...] - 16 qubits simultaneously
→ All MUXes are synchronized at each step boundary
```

### Box Constraints

Synchronized scheduling respects box (筐体) constraints:

- **Box A only**: 4 synchronized steps (A handles both control and readout)
- **Box B + A Mixed**: 8 synchronized steps (see Box B Module Sharing below)

For a full chip calibration with mixed boxes, expect **12 steps** (4 A + 8 MIXED).

### Box B Module Sharing

Each Box B module controls 8 qubits (2 MUXes worth), but **Box B has no readout capability**. MIXED MUXes require Box A for readout, which creates a hardware constraint:

```
Box B Module Structure:
┌─────────────────────────────────────┐
│              Box B Module            │
│  (controls 8 qubits, no readout)    │
├──────────────┬──────────────────────┤
│    MUX N     │      MUX N+4         │
│  (4 qubits)  │    (4 qubits)        │
└──────────────┴──────────────────────┘
        │                  │
        ▼                  ▼
   Uses Box A         Uses Box A
   for readout        for readout
```

**Constraint**: MUXes that share the same Box B module cannot calibrate simultaneously because they compete for Box A readout resources.

**Solution**: The scheduler groups MIXED MUXes by their Box B module and executes each group sequentially:

```
MIXED Scheduling with Box B Sharing:
Group 1: [MUX 0, MUX 3, ...]  - 4 steps (one MUX from each Box B module)
Group 2: [MUX 4, MUX 7, ...]  - 4 steps (the other MUX from each Box B module)
Total: 8 steps for MIXED

Example for 64Qv3 (16 MUXes, 6 MIXED MUXes):
Box B modules: R21B→[0,4], U10B→[3,7], U13B→[10,14]
Group 1: [0, 3, 10]  → Steps 0-3
Group 2: [4, 7, 14]  → Steps 4-7
```

### Usage

```python
from qdash.workflow.engine.calibration import OneQubitScheduler

scheduler = OneQubitScheduler(chip_id="64Qv3")

# Generate synchronized schedule with checkerboard pattern
schedule = scheduler.generate_synchronized(
    qids=[str(i) for i in range(64)],
    use_checkerboard=True,
)

# Or from MUX IDs
schedule = scheduler.generate_synchronized_from_mux(
    mux_ids=list(range(16)),
    use_checkerboard=True,
)

# Execute synchronized steps
for step in schedule.steps:
    print(f"Step {step.step_index} ({step.box_type}):")
    print(f"  Parallel qubits: {step.parallel_qids}")

    # Execute all qubits in step.parallel_qids simultaneously
    execute_parallel(step.parallel_qids)
```

### SynchronizedOneQubitScheduleResult

The result object provides convenient methods:

```python
# Get all steps for a specific box type
box_a_steps = schedule.get_steps_by_box("A")

# Total number of steps
print(f"Total steps: {schedule.total_steps}")

# Box types in execution order
print(f"Box types: {schedule.box_types}")

# Serialize to dictionary
schedule_dict = schedule.to_dict()
```

### Integration with Calibration Flow

```python
from prefect import flow, task
from qdash.workflow.engine.calibration import OneQubitScheduler
from qdash.workflow.flow import init_calibration, get_session, finish_calibration

@task
def calibrate_qubits_parallel(qids: list[str], tasks: list[str]) -> dict:
    """Execute calibration tasks for multiple qubits in parallel."""
    session = get_session()
    results = {}
    # Use Prefect's parallel execution or hardware-level parallelism
    for qid in qids:
        results[qid] = {}
        for task_name in tasks:
            results[qid][task_name] = session.execute_task(task_name, qid)
    return results

@flow
def synchronized_calibration(username: str, chip_id: str):
    """Calibration with synchronized step execution."""
    scheduler = OneQubitScheduler(chip_id=chip_id)

    # Generate synchronized schedule
    schedule = scheduler.generate_synchronized_from_mux(
        mux_ids=list(range(16)),
        use_checkerboard=True,
    )

    qids = [str(i) for i in range(64)]
    init_calibration(username, chip_id, qids)

    tasks = ["CheckRabi", "CheckT1", "CheckT2Echo"]

    # Execute steps sequentially, qubits within each step in parallel
    for step in schedule.steps:
        # All qubits in step.parallel_qids are calibrated simultaneously
        results = calibrate_qubits_parallel(step.parallel_qids, tasks)
        print(f"Completed step {step.step_index}")

    finish_calibration()
```

### Comparison: Original vs Synchronized

| Aspect    | Original (`generate`)         | Synchronized (`generate_synchronized`) |
| --------- | ----------------------------- | -------------------------------------- |
| Output    | `parallel_groups` (MUX-based) | `steps` (synchronized)                 |
| Execution | MUXes independent             | All MUXes synchronized                 |
| Timing    | Steps may misalign            | Steps guaranteed aligned               |
| Use case  | When MUX independence is OK   | When synchronization required          |
| Steps     | ~3 stages (A, B, Mixed)       | 12 steps (4 A + 8 MIXED)               |

## References

- [1-Qubit Scheduler](./one-qubit-scheduler.md) - Core scheduler documentation
- [Square Lattice Topology](./square-lattice-topology.md) - Chip layout details
- Source: `src/qdash/workflow/engine/calibration/scheduler/one_qubit_plugins.py`
- Source: `src/qdash/workflow/engine/calibration/scheduler/one_qubit_scheduler.py`
- Tests: `tests/qdash/workflow/engine/calibration/scheduler/test_one_qubit_plugins.py`
- Tests: `tests/qdash/workflow/engine/calibration/scheduler/test_one_qubit_scheduler.py`
