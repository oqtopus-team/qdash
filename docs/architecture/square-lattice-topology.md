# Square Lattice Topology

QDash supports superconducting quantum processors with square lattice topology, where qubits are arranged in a 2D grid with nearest-neighbor coupling.

## Overview

### Supported Chip Sizes

- **64-qubit chip**: 8×8 grid (e.g., 64Qv3)
- **144-qubit chip**: 12×12 grid (e.g., 144Qv2)

## Physical Layout

### MUX-based Organization

Qubits are organized into **MUX units**, where each MUX controls 4 qubits arranged in a 2×2 sub-grid:

```
MUX Structure (4 qubits per MUX):
┌─────┬─────┐
│  0  │  1  │  (TL: Top-Left, TR: Top-Right)
├─────┼─────┤
│  2  │  3  │  (BL: Bottom-Left, BR: Bottom-Right)
└─────┴─────┘
```

### 64-Qubit Chip (8×8 Grid)

- **Grid size**: 8×8 = 64 qubits
- **MUX grid**: 4×4 = 16 MUXes
- **Each MUX**: Controls 4 qubits

**MUX Layout (4×4 grid of MUXes):**

```
┌──────┬──────┬──────┬──────┐
│ MUX0 │ MUX1 │ MUX2 │ MUX3 │
├──────┼──────┼──────┼──────┤
│ MUX4 │ MUX5 │ MUX6 │ MUX7 │
├──────┼──────┼──────┼──────┤
│ MUX8 │ MUX9 │MUX10 │MUX11 │
├──────┼──────┼──────┼──────┤
│MUX12 │MUX13 │MUX14 │MUX15 │
└──────┴──────┴──────┴──────┘
```

**Qubit ID Mapping:**

- MUX 0 controls qubits: 0, 1, 2, 3
- MUX 1 controls qubits: 4, 5, 6, 7
- MUX N controls qubits: 4N, 4N+1, 4N+2, 4N+3

**Full 64-qubit layout (8×8 grid):**

```
  0   1 | 4   5 | 8   9 | 12  13
  2   3 | 6   7 | 10  11| 14  15
  ------+-------+-------+-------
  16  17| 20  21| 24  25| 28  29
  18  19| 22  23| 26  27| 30  31
  ------+-------+-------+-------
  32  33| 36  37| 40  41| 44  45
  34  35| 38  39| 42  43| 46  47
  ------+-------+-------+-------
  48  49| 52  53| 56  57| 60  61
  50  51| 54  55| 58  59| 62  63
```

### 144-Qubit Chip (12×12 Grid)

- **Grid size**: 12×12 = 144 qubits
- **MUX grid**: 6×6 = 36 MUXes
- **Each MUX**: Controls 4 qubits

## Qubit ID to Coordinate Conversion

### Algorithm

Given a qubit ID `qid` and grid size `N`:

```python
def qid_to_coords(qid: int, grid_size: int) -> tuple[int, int]:
    """Convert qubit ID to (row, col) coordinates."""
    # Which MUX does this qubit belong to?
    mux_id = qid // 4

    # Position within the MUX (0=TL, 1=TR, 2=BL, 3=BR)
    pos_in_mux = qid % 4

    # MUX grid dimension (N/2 × N/2)
    mux_grid_size = grid_size // 2

    # MUX position in MUX grid
    mux_row = mux_id // mux_grid_size
    mux_col = mux_id % mux_grid_size

    # Position within MUX (2×2 sub-grid)
    local_row = pos_in_mux // 2  # 0 (top) or 1 (bottom)
    local_col = pos_in_mux % 2   # 0 (left) or 1 (right)

    # Combine to get global position
    row = mux_row * 2 + local_row
    col = mux_col * 2 + local_col

    return (row, col)
```

### Examples (64-qubit chip, N=8)

| Qubit ID | MUX | Pos in MUX | MUX Position | Local (r,c) | Global (row, col) |
| -------- | --- | ---------- | ------------ | ----------- | ----------------- |
| 0        | 0   | 0 (TL)     | (0, 0)       | (0, 0)      | (0, 0)            |
| 1        | 0   | 1 (TR)     | (0, 0)       | (0, 1)      | (0, 1)            |
| 2        | 0   | 2 (BL)     | (0, 0)       | (1, 0)      | (1, 0)            |
| 3        | 0   | 3 (BR)     | (0, 0)       | (1, 1)      | (1, 1)            |
| 4        | 1   | 0 (TL)     | (0, 1)       | (0, 0)      | (0, 2)            |
| 16       | 4   | 0 (TL)     | (1, 0)       | (0, 0)      | (2, 0)            |
| 17       | 4   | 1 (TR)     | (1, 0)       | (0, 1)      | (2, 1)            |

## Coupling Topology

### Nearest-Neighbor Connectivity

Qubits are coupled to their **nearest neighbors** in the 2D grid:

- **Horizontal edges**: Connect qubits in the same row (r1 == r2, |c1 - c2| = 1)
- **Vertical edges**: Connect qubits in the same column (c1 == c2, |r1 - r2| = 1)

### Edge Classification

Edges can be classified as:

1. **Intra-MUX edges**: Both qubits in the same MUX
   - Example: 0-1, 0-2, 1-3, 2-3 (within MUX 0)
   - Faster execution due to shared MUX resources

2. **Inter-MUX edges**: Qubits in different MUXes
   - Example: 1-4 (MUX 0 → MUX 1), 0-16 (MUX 0 → MUX 4)
   - Slower execution due to cross-MUX communication

### Total Edge Counts

**64-qubit chip (8×8 grid):**

- Horizontal edges: 8 rows × 7 edges/row = 56 edges
- Vertical edges: 7 rows × 8 edges/row = 56 edges
- **Total: 112 nearest-neighbor edges**

**144-qubit chip (12×12 grid):**

- Horizontal edges: 12 rows × 11 edges/row = 132 edges
- Vertical edges: 11 rows × 12 edges/row = 132 edges
- **Total: 264 nearest-neighbor edges**

## MUX Resource Conflicts

### Conflict Types

MUXes conflict if they share:

1. **Readout module**: Cannot measure simultaneously
2. **Control module**: Cannot apply control pulses simultaneously

### Wiring Configuration

The wiring configuration (`wiring.yaml`) defines:

```yaml
64Qv3:
  - mux: 0
    read_out: "M0-ch0"
    ctrl: ["OPX1-ch1", "OPX1-ch2"]
  - mux: 1
    read_out: "M0-ch1"
    ctrl: ["OPX1-ch3", "OPX1-ch4"]
  # ... more MUXes
```

### Conflict Detection Algorithm

```python
def build_mux_conflict_map(wiring_config):
    """Build conflict map from wiring configuration."""
    conflicts = {}

    # Group MUXes by shared readout module
    readout_groups = group_by_module(wiring_config, "read_out")

    # Group MUXes by shared control module
    control_groups = group_by_module(wiring_config, "ctrl")

    # Merge conflicts
    for mux_a, mux_b in all_pairs_in_same_group(readout_groups):
        conflicts[mux_a].add(mux_b)

    for mux_a, mux_b in all_pairs_in_same_group(control_groups):
        conflicts[mux_a].add(mux_b)

    return conflicts
```

## CR Gate Constraints

### Frequency Directionality

CR (Cross-Resonance) gates require:

**f_control < f_target**

This constraint filters out approximately 50% of coupling edges, leaving only valid CR pairs.

### Distance-2 Constraint

For parallel CR gate execution, pairs must satisfy the **distance-2 constraint**:

- No two pairs share a qubit (distance-0)
- No two pairs are adjacent in the coupling graph (distance-1)
- Pairs must be at least **2 hops apart** (distance-2)

**Example violation:**

```
Pair A: 0-1
Pair B: 1-4
Violation: Share qubit 1 (distance-0) ❌

Pair A: 0-1
Pair B: 1-2
Violation: Adjacent via qubit 1 (distance-1) ❌

Pair A: 0-1
Pair B: 4-5
Valid: Distance-2 separation ✓
```

## Coordinate System

### Row and Column Indexing

- **Row index**: 0 (top) to N-1 (bottom)
- **Column index**: 0 (left) to N-1 (right)
- **Origin**: Top-left corner (0, 0)

### Edge Naming Convention

Edges are named as `"q1-q2"` where:

- `q1` is the lower qubit ID
- `q2` is the higher qubit ID
- Example: `"0-1"`, `"16-17"`, `"1-4"`

## Visualization Tools

### Available Tools

1. **`src/tools/cr_scheduler_visualizer.py`**
   - Visualizes CR schedule with color-coded groups
   - Shows qubit lattice layout
   - Highlights MUX boundaries

2. **`src/tools/device_topology_generator.py`**
   - Generates device topology configurations
   - Exports coupling graph data

### Usage

```bash
# Generate CR schedule visualization
python src/tools/cr_scheduler_visualizer.py

# Output: .tmp/schedule_output/combined_schedule.png
```

## References

- Wiring configuration: `/workspace/qdash/config/qubex/{chip_id}/config/wiring.yaml`
- CR Scheduler implementation: `src/qdash/workflow/engine/calibration/cr_scheduler.py`
- Visualization tools: `src/tools/`
