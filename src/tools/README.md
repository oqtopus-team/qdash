# QDash Tools

Collection of utility scripts for QDash development and debugging.

## CR Scheduler Tools

### cr_scheduler_visualizer.py

Simple visualization tool for CR gate schedules. Generates schedule statistics and visualization images.

**Features:**

- Console output with schedule statistics
- Combined schedule visualization (all groups color-coded)
- Individual group visualizations

**Usage:**

```bash
python src/tools/cr_scheduler_visualizer.py
```

**Output:**

- Console: Schedule summary with filtering stats, group breakdown
- Files in `.tmp/schedule_output/`:
  - `combined_schedule.png`: All groups with color-coded edges
  - `schedule_group_N.png`: Individual visualizations for each group

**Configuration:**
Edit constants in the script to customize:

- `DEFAULT_CHIP_ID`: Chip to analyze (default: "64Qv3")
- `DEFAULT_USERNAME`: Username for database access (default: "orangekame3")
- `MAX_PARALLEL_OPS`: Maximum parallel operations per group (default: 10)
- `SCHEDULE_OUTPUT_DIR`: Output directory (default: ".tmp/schedule_output")

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
