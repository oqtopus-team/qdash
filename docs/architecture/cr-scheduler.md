# CR Gate Scheduler

The CR (Cross-Resonance) gate scheduler generates optimized execution schedules for two-qubit gate calibration on superconducting quantum processors.

## Overview

### Purpose

The scheduler solves the parallel CR gate scheduling problem:

**Given:**

- A set of qubit pairs (couplings) that can perform CR gates
- Hardware resource constraints (MUX conflicts, frequency directionality)
- Quality requirements (X90 gate fidelity thresholds)

**Output:**

- A sequence of parallel groups where each group contains CR pairs that can execute simultaneously without conflicts

### Key Features

- **Design-based direction inference**: Infers CR direction from chip design without frequency calibration
- **Frequency directionality filtering**: Only schedules CR pairs where f_control < f_target
- **MUX conflict detection**: Prevents resource contention from shared readout/control modules
- **Greedy graph coloring**: Uses NetworkX's graph coloring algorithms for parallel grouping
- **Fast/slow pair separation**: Prioritizes intra-MUX pairs (fast) before inter-MUX pairs (slow)
- **Configurable strategies**: Supports multiple coloring strategies (largest_first, smallest_last, etc.)
- **Plugin architecture**: Extensible filter and scheduler pipeline for custom logic

## Architecture

### Class Structure

```python
from qdash.workflow.engine.calibration.cr_scheduler import CRScheduler

# Initialize scheduler
scheduler = CRScheduler(
    username="alice",
    chip_id="64Qv3",
    wiring_config_path=None  # Optional, defaults to standard path
)

# Generate schedule
result = scheduler.generate(
    candidate_qubits=None,      # Optional: filter to specific qubits
    max_parallel_ops=10,        # Max pairs per group
    coloring_strategy="largest_first"
)

# Access results
parallel_groups = result.parallel_groups  # [[(c, t), ...], ...]
metadata = result.metadata                # Statistics
filtering_stats = result.filtering_stats  # Filtering info
```

### Result Object

`CRScheduleResult` contains:

```python
class CRScheduleResult:
    parallel_groups: list[list[tuple[str, str]]]
    metadata: dict[str, Any]
    filtering_stats: dict[str, int]
    _cr_pairs_string: list[str]
    _qid_to_mux: dict[str, int]
    _mux_conflict_map: dict[int, set[int]]
```

**Metadata fields:**

- `total_pairs`: Total CR pairs in schedule
- `scheduled_pairs`: Number of pairs actually scheduled
- `fast_pairs`: Intra-MUX pairs
- `slow_pairs`: Inter-MUX pairs
- `num_groups`: Number of parallel groups
- `max_parallel_ops`: Maximum operations per group
- `coloring_strategy`: Graph coloring strategy used
- `candidate_qubits_count`: Number of candidate qubits (if filtered)

## Scheduling Algorithm

### Step 1: Data Loading and Filtering

```python
# Load chip data from MongoDB
chip_doc = ChipDocument.get_current_chip(username)
qubit_frequency = extract_qubit_frequency(chip_doc.qubits)

# Get all coupling pairs
all_pairs = get_two_qubit_pair_list(chip_doc)

# Filter by candidate qubits (if provided)
if candidate_qubits:
    all_pairs = filter_by_candidates(all_pairs, candidate_qubits)

# Filter by frequency directionality (f_control < f_target)
cr_pairs = [
    pair for pair in all_pairs
    if qubit_frequency[q1] < qubit_frequency[q2]
]
```

### Step 2: MUX Configuration

```python
# Load wiring configuration
wiring_config = load_wiring_config(chip_id)

# Build MUX conflict map
mux_conflict_map = build_mux_conflict_map(wiring_config)

# Build qubit-to-MUX mapping
qid_to_mux = build_qubit_to_mux_map(wiring_config)
```

### Step 3: Fast/Slow Pair Separation

```python
fast_pairs = [
    pair for pair in cr_pairs
    if qid_to_mux[q1] == qid_to_mux[q2]  # Same MUX
]

slow_pairs = [
    pair for pair in cr_pairs
    if qid_to_mux[q1] != qid_to_mux[q2]  # Different MUXes
]
```

### Step 4: Conflict Graph Construction

For each pair group (fast, then slow), build a conflict graph:

```python
conflict_graph = nx.Graph()
conflict_graph.add_nodes_from(cr_pairs)

for pair_a, pair_b in combinations(cr_pairs, 2):
    q1a, q2a = pair_a.split("-")
    q1b, q2b = pair_b.split("-")

    # Conflict 1: Shared qubits
    if shared_qubits(pair_a, pair_b):
        conflict_graph.add_edge(pair_a, pair_b)

    # Conflict 2: Same MUX usage
    elif same_mux(pair_a, pair_b, qid_to_mux):
        conflict_graph.add_edge(pair_a, pair_b)

    # Conflict 3: MUX resource conflicts
    elif mux_conflict(pair_a, pair_b, mux_conflict_map):
        conflict_graph.add_edge(pair_a, pair_b)
```

### Step 5: Greedy Graph Coloring

```python
# Apply graph coloring
coloring = nx.coloring.greedy_color(
    conflict_graph,
    strategy="largest_first"  # Or other strategies
)

# Group pairs by color
color_groups = defaultdict(list)
for pair, color in coloring.items():
    color_groups[color].append(pair)

# Convert to sorted list
groups = [color_groups[c] for c in sorted(color_groups)]
```

### Step 6: Group Size Limiting

```python
# Split groups that exceed max_parallel_ops
if max_parallel_ops:
    split_groups = []
    for group in groups:
        for i in range(0, len(group), max_parallel_ops):
            chunk = group[i : i + max_parallel_ops]
            split_groups.append(chunk)
```

## Conflict Detection

### Conflict Type 1: Shared Qubits

Two pairs conflict if they share any qubit:

```python
pair_a = "0-1"
pair_b = "1-4"
# Conflict: Share qubit 1 ❌
```

### Conflict Type 2: Same MUX Usage

Two pairs conflict if they use the same MUX:

```python
pair_a = "0-1"  # MUX 0
pair_b = "2-3"  # MUX 0
# Conflict: Both use MUX 0 ❌
```

### Conflict Type 3: MUX Resource Conflicts

Two pairs conflict if their MUXes share readout or control modules:

```python
pair_a = "0-1"  # MUX 0 (uses readout M0-ch0)
pair_b = "4-5"  # MUX 1 (uses readout M0-ch1)

# If MUX 0 and MUX 1 share module M0:
# Conflict: Shared readout module ❌
```

## Graph Coloring Strategies

### Available Strategies

| Strategy                   | Description                    | Performance | Quality  |
| -------------------------- | ------------------------------ | ----------- | -------- |
| `largest_first`            | Largest degree first (default) | Fast        | Good     |
| `smallest_last`            | Smallest degree last           | Medium      | Better   |
| `saturation_largest_first` | DSATUR algorithm               | Slow        | Best     |
| `random_sequential`        | Random order                   | Fast        | Variable |
| `connected_sequential_bfs` | BFS ordering                   | Medium      | Good     |
| `connected_sequential_dfs` | DFS ordering                   | Medium      | Good     |

**Recommendation**: Use `largest_first` for most cases (good balance of speed and quality).

### Example Comparison

For a 64-qubit chip with 56 CR pairs:

```python
# largest_first
result = scheduler.generate(coloring_strategy="largest_first")
# → 12 groups, avg 4.67 pairs/group, fast execution

# saturation_largest_first
result = scheduler.generate(coloring_strategy="saturation_largest_first")
# → 10 groups, avg 5.6 pairs/group, slower execution
```

## Plugin Architecture (New)

### Overview

The scheduler now supports a pluggable architecture for filters and schedulers, enabling users to customize the scheduling pipeline with their own logic.

### Architecture Components

**Base Interfaces:**

- `CRPairFilter`: Base class for filtering CR pairs
- `CRSchedulingStrategy`: Base class for scheduling strategies
- `FilterContext`: Context object passed to filters (chip data, frequencies, MUX mapping)
- `ScheduleContext`: Context object passed to schedulers (MUX configuration, conflicts)

**Built-in Filters:**

- `CandidateQubitFilter`: Filter by candidate qubit set
- `FrequencyDirectionalityFilter`: Filter by frequency direction (design-based or measured)
- `FidelityFilter`: Filter by qubit fidelity threshold

**Built-in Schedulers:**

- `MuxConflictScheduler`: Graph coloring based on MUX conflicts
- `IntraThenInterMuxScheduler`: Schedule intra-MUX pairs first, then inter-MUX pairs

### Plugin Usage

#### Basic Plugin Usage

```python
from qdash.workflow.engine.calibration.cr_scheduler import CRScheduler
from qdash.workflow.engine.calibration.cr_scheduler_plugins import (
    CandidateQubitFilter,
    FrequencyDirectionalityFilter,
    FidelityFilter,
    IntraThenInterMuxScheduler,
    MuxConflictScheduler,
)

scheduler = CRScheduler(username="alice", chip_id="64Qv3")

# Custom filter pipeline
filters = [
    CandidateQubitFilter(["0", "1", "2", "3"]),
    FrequencyDirectionalityFilter(use_design_based=True),
    FidelityFilter(min_fidelity=0.95),
]

# Custom scheduler
custom_scheduler = IntraThenInterMuxScheduler(
    inner_scheduler=MuxConflictScheduler(
        max_parallel_ops=10,
        coloring_strategy="saturation_largest_first"
    )
)

# Generate with plugins
result = scheduler.generate_with_plugins(
    filters=filters,
    scheduler=custom_scheduler
)
```

#### Design-Based vs. Measured Direction

```python
# Option 1: Design-based (no frequency calibration required)
filters = [
    FrequencyDirectionalityFilter(use_design_based=True),
]

# Option 2: Measured (uses calibrated frequencies)
filters = [
    FrequencyDirectionalityFilter(use_design_based=False),
]

# Option 3: Auto-select (uses measured if available, else design-based)
filters = None  # Default behavior
```

### Creating Custom Filters

```python
from qdash.workflow.engine.calibration.cr_scheduler_plugins import (
    CRPairFilter,
    FilterContext,
)

class MyCustomFilter(CRPairFilter):
    """Custom filter example."""

    def __init__(self, threshold: float):
        self.threshold = threshold
        self._filtered_count = 0
        self._total_count = 0

    def filter(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Apply custom filtering logic."""
        self._total_count = len(pairs)

        # Your custom logic here
        filtered = [
            pair for pair in pairs
            if self._meets_criteria(pair, context)
        ]

        self._filtered_count = len(filtered)
        return filtered

    def _meets_criteria(self, pair: str, context: FilterContext) -> bool:
        """Custom criteria logic."""
        # Example: Check distance between qubits
        q1, q2 = pair.split("-")
        # ... custom logic ...
        return True

    def get_stats(self) -> dict[str, Any]:
        """Return statistics."""
        return {
            "filter_name": "my_custom_filter",
            "input_pairs": self._total_count,
            "output_pairs": self._filtered_count,
            "threshold": self.threshold,
        }
```

### Creating Custom Schedulers

```python
from qdash.workflow.engine.calibration.cr_scheduler_plugins import (
    CRSchedulingStrategy,
    ScheduleContext,
)

class MyCustomScheduler(CRSchedulingStrategy):
    """Custom scheduler example."""

    def __init__(self, param: int):
        self.param = param
        self._num_groups = 0

    def schedule(self, pairs: list[str], context: ScheduleContext) -> list[list[str]]:
        """Apply custom scheduling logic."""
        # Your custom grouping logic here
        groups = []

        # Example: Simple sequential grouping
        for pair in pairs:
            groups.append([pair])

        self._num_groups = len(groups)
        return groups

    def get_metadata(self) -> dict[str, Any]:
        """Return metadata."""
        return {
            "scheduler_name": "my_custom_scheduler",
            "param": self.param,
            "num_groups": self._num_groups,
        }
```

### Plugin Benefits

1. **Extensibility**: Add new filters/schedulers without modifying core code
2. **Reusability**: Share plugins across projects
3. **Testability**: Test components independently
4. **Flexibility**: Users can build custom pipelines
5. **Maintainability**: Clear separation of concerns

## Usage Examples

### Basic Usage

```python
from qdash.workflow.engine.calibration.cr_scheduler import CRScheduler

scheduler = CRScheduler(username="alice", chip_id="64Qv3")
result = scheduler.generate()

print(f"Generated {len(result.parallel_groups)} parallel groups")
for i, group in enumerate(result.parallel_groups, 1):
    print(f"Group {i}: {group}")
```

### With Candidate Qubits (Stage 1 Filtering)

```python
# Use only high-quality qubits from Stage 1 calibration
high_quality_qubits = ["0", "1", "2", "3", "16", "17", "18", "19"]

result = scheduler.generate(
    candidate_qubits=high_quality_qubits,
    max_parallel_ops=5
)
```

### Custom Wiring Configuration

```python
scheduler = CRScheduler(
    username="alice",
    chip_id="64Qv3",
    wiring_config_path="/custom/path/to/wiring.yaml"
)

result = scheduler.generate()
```

### Different Coloring Strategies

```python
# Try different strategies
for strategy in ["largest_first", "smallest_last", "saturation_largest_first"]:
    result = scheduler.generate(coloring_strategy=strategy)
    print(f"{strategy}: {len(result.parallel_groups)} groups")
```

## Performance Characteristics

### Typical Results (64-qubit chip)

Assuming ~50% of edges pass frequency filter (56 CR pairs from 112 total edges):

| Configuration                             | Groups | Avg Pairs/Group | Fast/Slow Split |
| ----------------------------------------- | ------ | --------------- | --------------- |
| Default (largest_first, max=10)           | 12-14  | 4-5             | 20/36           |
| Optimal (saturation_largest_first, max=∞) | 8-10   | 5-7             | 20/36           |
| Conservative (max=5)                      | 18-20  | 2-3             | 20/36           |

### Scaling

| Chip Size    | Total Edges | CR Pairs (~50%) | Expected Groups |
| ------------ | ----------- | --------------- | --------------- |
| 64Q (8×8)    | 112         | ~56             | 12-14           |
| 144Q (12×12) | 264         | ~132            | 25-30           |

## Integration with Workflow Engine

### Prefect Flow Integration

```python
from prefect import flow
from qdash.workflow.engine.calibration.cr_scheduler import CRScheduler

@flow
def calibrate_cr_gates(username: str, chip_id: str):
    # Generate schedule
    scheduler = CRScheduler(username, chip_id)
    result = scheduler.generate()

    # Execute each group in sequence
    for group_idx, group in enumerate(result.parallel_groups):
        # Execute group in parallel (within Prefect)
        for control, target in group:
            calibrate_cr_pair.submit(control, target)
```

## Error Handling

### Common Errors

**No qubit frequency data:**

```python
ValueError: No qubit frequency data found.
Please run qubit frequency calibration first.
```

**Wiring config not found:**

```python
FileNotFoundError: Wiring config not found:
/workspace/qdash/config/qubex/{chip_id}/config/wiring.yaml
```

**No valid CR pairs:**

```python
ValueError: No valid CR pairs after filtering
```

## Visualization

Use the visualizer tool to inspect schedules:

```bash
# Basic usage (legacy mode)
python src/tools/cr_scheduler_visualizer.py

# Plugin mode with design-based direction (default)
python src/tools/cr_scheduler_visualizer.py --use-plugins

# Plugin mode with measured frequency directionality
python src/tools/cr_scheduler_visualizer.py --use-plugins --measured

# Use simple MUX conflict scheduler (no intra/inter prioritization)
python src/tools/cr_scheduler_visualizer.py --use-plugins --scheduler mux-conflict

# With candidate qubits and fidelity filter
python src/tools/cr_scheduler_visualizer.py --use-plugins \
    --candidate-qubits 0 1 2 3 --min-fidelity 0.95

# Custom chip and user
python src/tools/cr_scheduler_visualizer.py --chip-id 144Qv1 --username alice

# Show all options
python src/tools/cr_scheduler_visualizer.py --help
```

**Command-line Options:**

- `--chip-id CHIP_ID` - Chip ID to use (default: 64Qv3)
- `--username USERNAME` - Username for chip data access (default: orangekame3)
- `--use-plugins` - Use plugin architecture instead of legacy mode
- `--candidate-qubits Q1 Q2 ...` - Candidate qubit IDs to filter
- `--min-fidelity THRESHOLD` - Minimum fidelity threshold (e.g., 0.95)
- `--measured` - Use measured frequency directionality (default is design-based)
- `--scheduler {mux-conflict,intra-then-inter}` - Scheduler strategy (default: intra-then-inter)

**Output:**

- Console: Schedule statistics and group breakdown
- Files: Timestamped directories (e.g., `.tmp/schedule_output_20250115_143022/`) with visual representations
  - `combined_schedule.png`: All groups with color-coded edges
  - `schedule_group_N.png`: Individual group visualizations

Each run creates a new timestamped directory, enabling easy comparison of different scheduler configurations or calibration data across multiple runs.

## References

- Core Implementation: `src/qdash/workflow/engine/calibration/cr_scheduler.py`
- Plugin Architecture: `src/qdash/workflow/engine/calibration/cr_scheduler_plugins.py`
- Core Tests: `tests/qdash/workflow/engine/calibration/test_cr_scheduler.py`
- Plugin Tests: `tests/qdash/workflow/engine/calibration/test_cr_scheduler_plugins.py`
- Visualization: `src/tools/cr_scheduler_visualizer.py`
- Topology: [Square Lattice Topology](./square-lattice-topology.md)
