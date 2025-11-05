# QDash Tools

Collection of utility scripts for QDash development and debugging.

## CR Scheduler Tools

### cr_scheduler_visualizer.py

CLI tool for visualizing CR gate schedules with support for both legacy and plugin architectures.

**Features:**

- Console output with schedule statistics
- Combined schedule visualization (all groups color-coded)
- Individual group visualizations
- Timestamped output directories for comparing multiple runs
- Support for plugin architecture with custom filters and schedulers
- Design-based frequency directionality inference

**Usage:**

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

- Console: Schedule summary with filtering stats, group breakdown
- Files in timestamped directories (e.g., `.tmp/schedule_output_20250115_143022/`):
  - `combined_schedule.png`: All groups with color-coded edges
  - `schedule_group_N.png`: Individual visualizations for each group

Each run creates a new timestamped directory, enabling easy comparison of different scheduler configurations or calibration data across runs.

---

### cr_schedule_generator.py

Legacy tool for generating CR schedules with X90 fidelity filtering.

**Usage:**

```bash
python src/tools/cr_schedule_generator.py
```

**Output:**

- Console: `parallel_groups` format for copy-paste into calibration scripts
- Files in `schedule/`: Visualization plots

---

## Other Tools

- `device_topology_generator.py`: Generate device topology configurations
- `get_two_qubit_pair.py`: Extract two-qubit coupling pairs
- `read_wiring.py`: Parse wiring configuration files
- `greedy.py`: Greedy graph coloring utilities
- `diagnose.py`: Diagnostic tools
- `converter.py`: Data format conversion utilities
