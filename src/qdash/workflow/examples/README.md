# Python Flow Examples

This directory contains template flows demonstrating the Python Flow Editor API.

## Templates

All example flows are located in the `templates/` directory:

### 1. Simple Flow (`templates/simple_flow.py`)

Basic sequential calibration demonstrating low-level API usage.

**Features:**

- Sequential task execution
- Direct use of `session.execute_task()`
- Error handling for individual qubits
- Good starting point for custom flows

**Usage:**

```python
from qdash.workflow.examples.templates.simple_flow import my_custom_flow

results = my_custom_flow(
    username="alice",
    chip_id="chip_1",
    qids=["32", "38"]
)
```

### 2. Custom Parallel Flow (`templates/custom_parallel_flow.py`)

Group-based parallel execution using Prefect's `@task` + `submit()`.

**Features:**

- True parallel execution across qubit groups
- Each group runs concurrently
- Sequential execution within each group
- Visible in Prefect UI as separate tasks

**Usage:**

```python
from qdash.workflow.examples.templates.custom_parallel_flow import custom_parallel_flow

results = custom_parallel_flow(
    username="alice",
    chip_id="chip_1"
    # Groups defined in the flow: ["33", "32"] and ["36", "38"]
)
```

### 3. Iterative Flow (`templates/iterative_flow.py`)

Advanced iterative calibration with parallel groups and custom parameters.

**Features:**

- Repeat parallel group calibration multiple times
- Custom task parameters per iteration
- Useful for stability testing or data collection
- Demonstrates task_details configuration

**Usage:**

```python
from qdash.workflow.examples.templates.iterative_flow import iterative_flow

results = iterative_flow(
    username="alice",
    chip_id="chip_1",
    max_iterations=3
    # Groups defined in the flow
)
```

### 4. Multi-Stage Adaptive Flow (`templates/multi_stage_adaptive_flow.py`) ⭐ NEW

Advanced multi-stage calibration with stage result recording and conditional execution.

**Features:**

- Record dynamically determined values during execution
- Use previous stage results to determine subsequent actions
- All stage results persisted to MongoDB for tracking
- Adaptive workflow based on quality metrics
- Clear stage boundaries with recorded metrics and decisions

**Usage:**

```python
from qdash.workflow.examples.templates.multi_stage_adaptive_flow import multi_stage_adaptive_flow

results = multi_stage_adaptive_flow(
    username="alice",
    chip_id="chip_1",
    qids=["0", "1", "2"]
)
```

**Example Pattern:**

```python
# Stage 1: Measure and record
stage1_results = {}
for qid in qids:
    result = session.execute_task("CheckFreq", qid)
    stage1_results[qid] = {
        "frequency": result.get("qubit_frequency"),
        "quality": "high" if result.get("contrast") > 0.8 else "low"
    }

# Record stage 1 results with decision logic
session.record_stage_result("stage1_frequency_scan", {
    "status": "completed",
    "qubits": stage1_results,
    "decision": "proceed_to_rabi" if all(r["quality"] == "high" for r in stage1_results.values()) else "retry"
})

# Stage 2: Use stage 1 results to determine actions
stage1_data = session.get_stage_result("stage1_frequency_scan")
if stage1_data["decision"] == "proceed_to_rabi":
    # Execute stage 2 tasks
    for qid in qids:
        session.execute_task("CheckRabi", qid)
```

### 5. Full Chip Calibration with CR Scheduling (`templates/full_chip_calibration_with_cr_scheduling.py`) ⭐ NEW

Complete chip calibration: 1-qubit → CR schedule generation → 2-qubit calibration.

**Features:**

- 1-qubit full calibration for all qubits
- CR schedule generation using engine-side `CRScheduler`
- 2-qubit coupling calibration following the generated schedule
- All scheduling decisions and results recorded for tracking
- Uses real hardware constraints (X90 fidelity, MUX conflicts)

**Usage:**

```python
from qdash.workflow.examples.templates.full_chip_calibration_with_cr_scheduling import full_chip_calibration_with_cr_scheduling

results = full_chip_calibration_with_cr_scheduling(
    username="alice",
    chip_id="64Qv3",
    qids=["0", "1", "2", "3"]
)
```

**Workflow:**

```python
# Stage 1: 1-qubit calibration
for qid in qids:
    session.execute_task("CheckRabi", qid)
    session.execute_task("CheckT1", qid)
    # ... more 1-qubit tasks

session.record_stage_result("stage1_one_qubit_calibration", {...})

# Stage 2: Generate CR schedule using engine-side CRScheduler
# Extract candidate qubits from Stage 1 (high and medium quality only)
stage1_data = session.get_stage_result("stage1_one_qubit_calibration")
stage1_qubits = stage1_data["qubits"]

high_quality = [qid for qid, r in stage1_qubits.items() if r.get("overall_quality") == "high"]
medium_quality = [qid for qid, r in stage1_qubits.items() if r.get("overall_quality") == "medium"]
candidate_qubits = high_quality + medium_quality

from qdash.workflow.engine.calibration.cr_scheduler import CRScheduler

scheduler = CRScheduler(username, chip_id)
schedule_result = scheduler.generate(
    candidate_qubits=candidate_qubits,  # Only use qubits that passed Stage 1!
    max_parallel_ops=10
)
cr_schedule = schedule_result.to_dict()

session.record_stage_result("stage2_cr_schedule_generation", {
    "schedule": cr_schedule,  # Includes parallel_groups, metadata, filtering stats
    "tool_used": "engine.calibration.CRScheduler",
    "input_summary": {
        "based_on_stage": "stage1_one_qubit_calibration",
        "candidate_qubits": candidate_qubits
    }
})

# Stage 3: Execute 2-qubit calibration according to schedule
for group in cr_schedule["parallel_groups"]:
    for (control, target) in group:
        session.execute_task("CheckCrossResonance", f"{control}-{target}")

session.record_stage_result("stage3_two_qubit_calibration", {...})
```

**Recorded Data:**

The CR schedule includes:

- `parallel_groups`: Optimized coupling groups for parallel execution
- `metadata`: Statistics (total pairs, fast/slow split, number of groups)
- `filtering_stats`: X90 fidelity filtering, frequency directionality

$1Pulling Latest Configuration

Pull latest config from GitHub before calibration:

```python
from qdash.workflow.helpers import init_calibration, GitHubPushConfig

session = init_calibration(
    username, chip_id, qids, flow_name=flow_name,
    enable_github_pull=True  # Pull latest config before starting
)
```

### Pushing Calibration Results

Push results to GitHub after calibration:

```python
from qdash.workflow.helpers import (
    init_calibration,
    finish_calibration,
    GitHubPushConfig,
    ConfigFileType,
)

# Configure GitHub push
session = init_calibration(
    username, chip_id, qids, flow_name=flow_name,
    enable_github_pull=True,
    github_push_config=GitHubPushConfig(
        enabled=True,
        file_types=[
            ConfigFileType.CALIB_NOTE,  # Push calib_note.json
            ConfigFileType.PROPS,       # Push props.yaml (with merge logic)
        ],
        commit_message=f"Update calibration results for {chip_id}",
        branch="main"
    )
)

# Calibration logic...

# Push results to GitHub
push_results = finish_calibration()
print(f"GitHub push results: {push_results}")
```

### Available File Types

- `ConfigFileType.CALIB_NOTE` - calibration/calib_note.json (direct copy)
- `ConfigFileType.PROPS` - params/props.yaml (uses existing merge logic)
- `ConfigFileType.PARAMS` - params/params.yaml (direct copy)
- `ConfigFileType.ALL_PARAMS` - All \*.yaml files in params/ directory

### Environment Variables Required

Set these environment variables for GitHub integration:

```bash
GITHUB_USER=your-username
GITHUB_TOKEN=your-personal-access-token
CONFIG_REPO_URL=https://github.com/your-org/your-config-repo.git
```

### Example in Templates

All templates include commented-out GitHub integration examples.
Simply uncomment and configure to enable:

```python
# Optional: GitHub integration (uncomment to enable)
# from qdash.workflow.helpers import GitHubPushConfig, ConfigFileType
# init_calibration(
#     username, chip_id, qids, flow_name=flow_name,
#     enable_github_pull=True,
#     github_push_config=GitHubPushConfig(
#         enabled=True,
#         file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.PROPS]
#     )
# )
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

**Schedule-based Execution:**

- `execute_schedule()` - Execute tasks according to schedule definition (SerialNode, ParallelNode, BatchNode)

### FlowSession Methods

**Task Execution:**

- `execute_task(task_name, qid, task_details)` - Execute a single task

**Parameter Management:**

- `get_parameter(qid, param_name)` - Get parameter value
- `set_parameter(qid, param_name, value)` - Set parameter value

**Stage Result Recording (New):**

- `record_stage_result(stage_name, result)` - Record stage execution results
- `get_stage_result(stage_name)` - Retrieve recorded stage results

**Session Completion:**

- `finish_calibration()` - Complete calibration

## Parallel Execution Examples

### Using `calibrate_parallel()`

True parallel execution across qubits:

```python
from qdash.workflow.helpers import calibrate_parallel

results = calibrate_parallel(
    qids=["0", "1", "2"],
    tasks=["CheckFreq", "CheckRabi"]
)
```

### Using `parallel_map()` for Custom Logic

Apply custom logic in parallel with Prefect UI visibility:

```python
from qdash.workflow.helpers import parallel_map, get_session

def my_adaptive_logic(qid, threshold, max_iter):
    session = get_session()
    for iteration in range(max_iter):
        result = session.execute_task("CheckFreq", qid)
        # Your convergence logic
        if converged:
            break
    return result

results = parallel_map(
    items=["0", "1", "2"],
    func=my_adaptive_logic,
    task_name_func=lambda qid: f"adaptive-Q{qid}",
    threshold=0.01,
    max_iter=10
)
```

### Using `execute_schedule()` for Complex Orchestration

Custom schedule-based execution:

```python
from qdash.datamodel.menu import SerialNode, ParallelNode, BatchNode
from qdash.workflow.helpers import execute_schedule

# Complex nested schedule
schedule = SerialNode(serial=[
    ParallelNode(parallel=["0", "1"]),  # Q0 and Q1
    "2",                                 # Q2
    BatchNode(batch=["0", "1", "2"])    # All together
])

results = execute_schedule(
    tasks=["CheckFreq", "CheckRabi"],
    schedule=schedule
)
```

## Template Customization

All templates include:

- `username` and `chip_id` - Automatically provided from UI properties
- `qids` - Qubit IDs (can be hardcoded or parameterized)
- `flow_name` - Automatically injected by API for display in execution list

Edit the TODO comments in each template to customize:

- Qubit IDs
- Task lists
- Execution patterns
- Custom parameters
