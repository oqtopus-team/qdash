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

## API Tools

### get_latest_task_results.py

CLI tool for fetching latest task results and JSON figures from the QDash API. Supports both local and remote (Cloudflare Access protected) deployments.

**Features:**

- Fetch latest task results by chip ID and task name
- Support for qubit and coupling task types
- Download Plotly JSON figures for visualization
- Filter by specific qubit/coupling IDs
- Query historical results by date
- Multiple output formats (table, JSON)

**Environment Variables (`.env`):**

```bash
# Required for remote access
CF_ACCESS_CLIENT_ID="your-client-id.access"
CF_ACCESS_CLIENT_SECRET="your-client-secret"
CF_ACCESS_DOMAIN="https://your-domain.example.com"
QDASH_API_TOKEN="your-api-token"

# Optional for local development
API_PORT=2004  # Default local port
```

**Usage:**

```bash
# Basic usage - get latest results
python src/tools/get_latest_task_results.py --chip-id 64Qv3 --task CheckRabi

# Get coupling task results
python src/tools/get_latest_task_results.py --chip-id 64Qv3 --task CheckCZ --type coupling

# Get historical results for a specific date
python src/tools/get_latest_task_results.py --chip-id 64Qv3 --task CheckRabi --date 20241213

# Output as JSON
python src/tools/get_latest_task_results.py --chip-id 64Qv3 --task CheckRabi --output json

# Download all JSON figures
python src/tools/get_latest_task_results.py --chip-id 64Qv3 --task CheckRabi --download-figures ./figures

# Download figures for specific qubit IDs only
python src/tools/get_latest_task_results.py --chip-id 64Qv3 --task CheckRabi --download-figures ./figures --qids 0,1,2
```

**Command-line Options:**

- `--chip-id CHIP_ID` - Chip ID (required)
- `--task TASK` - Task name (required, e.g., CheckRabi, CheckCZ)
- `--type {qubit,coupling}` - Task type (default: qubit)
- `--date YYYYMMDD` - Date for historical results
- `--output {table,json}` - Output format (default: table)
- `--download-figures DIR` - Download JSON figures to directory
- `--qids IDS` - Comma-separated qubit/coupling IDs to filter
- `--base-url URL` - Override API base URL
- `--token TOKEN` - API token (or set `QDASH_API_TOKEN`)
- `--cf-client-id ID` - Cloudflare Access Client ID
- `--cf-client-secret SECRET` - Cloudflare Access Client Secret

**Output:**

- Table format: Summary with ID, status, timestamps, and figure count
- JSON format: Raw API response
- Figures: Plotly JSON files named `{task}_{id}.json`

---

## Other Tools

- `device_topology_generator.py`: Generate device topology configurations
- `get_two_qubit_pair.py`: Extract two-qubit coupling pairs
- `read_wiring.py`: Parse wiring configuration files
- `greedy.py`: Greedy graph coloring utilities
- `diagnose.py`: Diagnostic tools
- `converter.py`: Data format conversion utilities
