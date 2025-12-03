# 1-Qubit Calibration Scheduler

The 1-qubit scheduler generates optimized execution schedules for single-qubit calibration based on box (筐体) constraints.

## Overview

### Purpose

The scheduler solves the parallel 1-qubit calibration scheduling problem:

**Given:**

- A set of qubits to calibrate
- Hardware box constraints (Box A, Box B modules)
- Wiring configuration defining MUX-to-module mappings

**Output:**

- A sequence of stages where each stage contains qubits that can execute without box conflicts
- Within each stage, qubits execute sequentially (same box constraint)
- Different stages can potentially execute in parallel (different boxes)

### Key Features

- **Box detection from wiring**: Automatically detects box type from module naming convention
- **MUX grouping**: Groups qubits by their MUX's box dependencies
- **Stage generation**: Creates execution stages for Box A, Box B, and Mixed qubits
- **Flexible configuration**: Supports custom wiring configuration paths

## Architecture

### Box Detection

Module names follow a naming convention that indicates box type:

```
Module names ending with 'A' → Box A (e.g., Q73A, R20A, S159A)
Module names ending with 'B' → Box B (e.g., R21B, U10B, U13B)
```

### MUX Classification

Each MUX is classified based on the modules it uses:

| Classification | Modules Used   | Example                               |
| -------------- | -------------- | ------------------------------------- |
| Box A          | Only A modules | MUX 1: ctrl=[Q73A-*], read_out=Q73A-8 |
| Box B          | Only B modules | (rare in current configs)             |
| Mixed          | Both A and B   | MUX 0: ctrl=[R21B-*], read_out=Q73A-1 |

### Conflict Rules

1. **Same box = Sequential**: Qubits using the same box type cannot execute in parallel
2. **Different box = Can be parallel**: Qubits on different boxes can execute in parallel
3. **Mixed = Conflicts with both**: MUXes using both box types conflict with Box A and Box B

## Usage

### Basic Usage

```python
from qdash.workflow.engine.calibration.scheduler import OneQubitScheduler

scheduler = OneQubitScheduler(chip_id="64Qv3")

# Generate schedule from qubit IDs
schedule = scheduler.generate(qids=["0", "1", "4", "5", "24", "25"])

# Access stages
for stage in schedule.stages:
    print(f"Stage {stage.box_type}: {stage.qids}")
```

### Integration with Calibration Flow

```python
from prefect import flow
from qdash.workflow.engine.calibration.scheduler import OneQubitScheduler
from qdash.workflow.flow import init_calibration, get_session, finish_calibration

@flow
def calibrate_chip(username: str, chip_id: str, qids: list[str]):
    # Generate schedule
    scheduler = OneQubitScheduler(chip_id=chip_id)
    schedule = scheduler.generate(qids=qids)

    # Execute each stage
    for stage in schedule.stages:
        # Each stage can be a separate execution session
        session = init_calibration(
            username, chip_id, stage.qids,
            flow_name=f"1Q_Calibration_{stage.box_type}"
        )

        # Execute qubits sequentially within stage
        for qid in stage.qids:
            session.execute_task("CheckRabi", qid)
            session.execute_task("CheckT1", qid)

        finish_calibration()
```

### Workflow Template Integration

```python
from dataclasses import dataclass

@dataclass
class OneQubitStage:
    """1-qubit calibration stage from scheduler."""
    box_type: str
    qids: list[str]
    tasks: list[str]

# Use with scheduler
scheduler = OneQubitScheduler(chip_id="64Qv3")
result = scheduler.generate(qids=all_qubits)

stages = [
    OneQubitStage(
        box_type=stage.box_type,
        qids=stage.qids,
        tasks=["CheckRabi", "CheckT1", "CheckT2Echo"]
    )
    for stage in result.stages
]
```

## Result Object

### OneQubitScheduleResult

```python
@dataclass
class OneQubitScheduleResult:
    stages: list[OneQubitStageInfo]  # Execution stages
    metadata: dict[str, Any]          # Statistics
    mux_box_map: dict[int, set[str]]  # MUX → box types
    qid_to_mux: dict[str, int]        # Qubit → MUX mapping
```

### OneQubitStageInfo

```python
@dataclass
class OneQubitStageInfo:
    box_type: str       # "A", "B", or "MIXED"
    qids: list[str]     # Qubit IDs (executed sequentially)
    mux_ids: set[int]   # MUX IDs in this stage
```

### Metadata Fields

- `total_qubits`: Total qubits scheduled
- `box_a_count`: Qubits using Box A only
- `box_b_count`: Qubits using Box B only
- `mixed_count`: Qubits using both box types
- `num_stages`: Number of execution stages
- `chip_id`: Chip identifier

## 64Qv3 Example

For a 64-qubit chip with the standard wiring configuration:

```
MUX Layout (4×4 grid):
┌──────┬──────┬──────┬──────┐
│ MUX0 │ MUX1 │ MUX2 │ MUX3 │  ← Mixed, A, A, Mixed
├──────┼──────┼──────┼──────┤
│ MUX4 │ MUX5 │ MUX6 │ MUX7 │  ← Mixed, A, A, Mixed
├──────┼──────┼──────┼──────┤
│ MUX8 │ MUX9 │MUX10 │MUX11 │  ← A, A, Mixed, A
├──────┼──────┼──────┼──────┤
│MUX12 │MUX13 │MUX14 │MUX15 │  ← A, A, Mixed, A
└──────┴──────┴──────┴──────┘
```

**Typical Stage Distribution:**

```python
scheduler = OneQubitScheduler(chip_id="64Qv3")
schedule = scheduler.generate(qids=[str(i) for i in range(64)])

# Results (varies by wiring config):
# Stage 1 (Box A): ~32-40 qubits (MUXes 1,2,5,6,8,9,11,12,13,15)
# Stage 2 (Mixed): ~24-32 qubits (MUXes 0,3,4,7,10,14)
```

## Debugging

### Get MUX Information

```python
scheduler = OneQubitScheduler(chip_id="64Qv3")
mux_info = scheduler.get_mux_info()

for mux_id, info in mux_info.items():
    print(f"MUX {mux_id}:")
    print(f"  Box: {info['box_label']}")
    print(f"  Qubits: {info['qids']}")
    print(f"  Types: {info['box_types']}")
```

### Visualize Schedule

```python
schedule = scheduler.generate(qids=["0", "4", "8", "12"])

for i, stage in enumerate(schedule.stages, 1):
    print(f"\n=== Stage {i} ({stage.box_type}) ===")
    print(f"Qubits: {stage.qids}")
    print(f"MUXes: {stage.mux_ids}")
```

## References

- Core Implementation: `src/qdash/workflow/engine/calibration/scheduler/one_qubit_scheduler.py`
- Tests: `tests/qdash/workflow/engine/calibration/scheduler/test_one_qubit_scheduler.py`
- CR Scheduler: [CR Gate Scheduler](./cr-scheduler.md)
- Topology: [Square Lattice Topology](./square-lattice-topology.md)
