# Python Flow Examples

This directory contains example calibration flows demonstrating the Python Flow Editor API.

## Examples

### 1. Parallel Calibration (`parallel_calibration_example.py`)

True parallel calibration using Prefect's `@task` + `submit()` pattern.

**Features:**

- True parallel execution across qubits
- Each qubit runs concurrently
- Visible in Prefect UI as separate tasks
- No deployment registration required

**Usage:**

```python
from qdash.workflow.examples.parallel_calibration_example import (
    parallel_calibration_example,
)

results = parallel_calibration_example(
    username="orangekame3",
    chip_id="64Qv3",
    qids=["32", "38"]
)
```

### 2. Adaptive Parallel Calibration (`adaptive_parallel_example.py`)

Parallel closed-loop calibration where each qubit independently iterates until convergence.

**Features:**

- Write your own convergence logic
- True parallel execution across qubits
- Each qubit appears separately in Prefect UI
- Full control over parameter updates and stopping criteria

**Usage:**

```python
from qdash.workflow.examples.adaptive_parallel_example import (
    adaptive_parallel_example,
)

results = adaptive_parallel_example(
    username="orangekame3",
    chip_id="64Qv3",
    qids=["32", "38"],
    threshold=0.01,
    max_iterations=10
)
```

### 3. Smart Calibration (`smart_calibration.py`)

Conditional calibration with branching logic based on measurement results.

**Features:**

- Conditional task execution
- Different calibration paths for different qubits
- Result-based decision making

**Usage:**

```python
from qdash.workflow.examples.smart_calibration import smart_calibration

results = smart_calibration(
    username="alice",
    execution_id="20240101-003",
    chip_id="chip_1",
    qids=["0", "1", "2"],
    frequency_threshold=5.0
)
```

### 4. Schedule-based Calibration (`schedule_calibration.py`)

Calibration orchestration using schedule definitions (SerialNode, ParallelNode, BatchNode).

**Features:**

- Schedule-based task orchestration
- Complex nested execution patterns
- Compatible with MenuModel schedules
- Flexible qubit grouping and sequencing

**Usage:**

```python
from qdash.workflow.examples.schedule_calibration import schedule_calibration

results = schedule_calibration(
    username="alice",
    execution_id="20240101-004",
    chip_id="chip_1",
    qids=["0", "1", "2"]
)
```

## Running Examples

### As Prefect Flows

```bash
# Deploy and run through Prefect
python -m qdash.workflow.examples.parallel_calibration_example
```

### Directly

Each example can also be run directly:

```bash
python src/qdash/workflow/examples/parallel_calibration_example.py
python src/qdash/workflow/examples/adaptive_parallel_example.py
python src/qdash/workflow/examples/smart_calibration.py
python src/qdash/workflow/examples/schedule_calibration.py
```

## Creating Custom Flows

Use these examples as templates for creating your own custom calibration flows:

```python
from prefect import flow
from qdash.workflow.helpers import (
    init_calibration,
    finish_calibration,
    get_session,
)

@flow
def my_custom_flow(username, execution_id, chip_id, qids):
    # Initialize session
    session = init_calibration(username, execution_id, chip_id)

    # Your custom calibration logic
    for qid in qids:
        result = session.execute_task("CheckFreq", qid)
        if result.get("qubit_frequency", 0) > 5.0:
            session.execute_task("CheckRabi", qid)

    # Complete calibration
    finish_calibration()
```

## API Reference

See the [Python Flow Helper Documentation](../helpers/) for complete API details.

### Key Functions

**Session Management:**

- `init_calibration()` - Initialize calibration session
- `get_session()` - Get current session
- `finish_calibration()` - Complete and save calibration

**Parallel Execution (Recommended):**

- `calibrate_parallel()` - True parallel execution across qubits using `@task` + `submit()`
- `parallel_map()` - Generic parallel map for custom logic with Prefect UI visibility

**Sequential Execution:**

- `calibrate_qubits_task_first()` - Execute tasks sequentially, processing all qubits for each task
- `calibrate_qubits_qubit_first()` - Execute tasks sequentially, completing all tasks for each qubit
- `execute_schedule()` - Execute tasks according to schedule definition (SerialNode, ParallelNode, BatchNode)

**Adaptive Calibration:**

- `adaptive_calibrate()` - Single qubit closed-loop helper
- Use `parallel_map()` for parallel adaptive calibration with custom convergence logic

### Execution Modes Explained

#### `calibrate_qubits_task_first(qids, tasks)` (Sequential)

```
Task1: Q0 → Q1 → Q2 (one after another)
Task2: Q0 → Q1 → Q2 (one after another)
Task3: Q0 → Q1 → Q2 (one after another)
```

Use when: Tasks are independent and you want to complete each task for all qubits before moving to the next task.

#### `calibrate_qubits_qubit_first(qids, tasks)` (Sequential)

```
Q0: Task1 → Task2 → Task3 (sequential)
Q1: Task1 → Task2 → Task3 (sequential)  ← Executed after Q0 completes
Q2: Task1 → Task2 → Task3 (sequential)  ← Executed after Q1 completes
```

Use when: Tasks have dependencies (e.g., CheckRabi needs CheckFreq results for the same qubit).

#### `execute_schedule(tasks, schedule)` (Schedule-based)

Execute tasks according to custom schedule definitions using schedule nodes:

- **SerialNode**: Process sub-nodes one after another
- **ParallelNode**: Process sub-nodes (sequentially in Python Flow)
- **BatchNode**: Execute tasks for multiple qubits together
- **String qid**: Execute tasks for a single qubit

Example:

```python
from qdash.datamodel.menu import SerialNode, ParallelNode, BatchNode

# Complex nested schedule
schedule = SerialNode(serial=[
    ParallelNode(parallel=["0", "1"]),  # Q0 and Q1
    "2",                                 # Q2
    BatchNode(batch=["0", "1", "2"])    # All together
])

results = execute_schedule(tasks=["CheckFreq", "CheckRabi"], schedule=schedule)
```

Use when: You need custom orchestration patterns that match MenuModel schedules or complex qubit grouping logic.

#### `calibrate_parallel(qids, tasks)` (True Parallel)

```
Q0: Task1 → Task2 → Task3  ┐
Q1: Task1 → Task2 → Task3  ├─ All run concurrently
Q2: Task1 → Task2 → Task3  ┘
```

Use when: You want true parallel execution across qubits using Prefect's `@task` + `submit()` pattern.

**Example:**

```python
from qdash.workflow.helpers import calibrate_parallel

results = calibrate_parallel(
    qids=["0", "1", "2"],
    tasks=["CheckFreq", "CheckRabi"]
)
```

#### `parallel_map(items, func)` (Custom Parallel Logic)

Apply a custom function to items in parallel with Prefect UI visibility.

Use when: You need custom logic (e.g., adaptive calibration with your own convergence criteria) running in parallel.

**Example:**

```python
from qdash.workflow.helpers import parallel_map, get_session

def my_adaptive_logic(qid, threshold, max_iter):
    session = get_session()
    # Your custom convergence logic
    for iteration in range(max_iter):
        result = session.execute_task("CheckFreq", qid)
        # Your convergence check
        if converged:
            break
    return result

results = parallel_map(
    items=["0", "1", "2"],
    func=my_adaptive_logic,
    task_name_func=lambda qid: f"adaptive-Q{qid}",  # Shows in Prefect UI
    threshold=0.01,
    max_iter=10
)
```

### FlowSession Methods

- `execute_task(task_name, qid, task_details)` - Execute a single task
- `get_parameter(qid, param_name)` - Get parameter value
- `set_parameter(qid, param_name, value)` - Set parameter value
- `finish_calibration()` - Complete calibration
