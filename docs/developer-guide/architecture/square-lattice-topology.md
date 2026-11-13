# Square Lattice Topology

QDash supports superconducting quantum processors with square lattice topology, where qubits are arranged in a 2D grid with nearest-neighbor coupling.

## Topology Model

### Supported Chip Sizes

- **16-qubit chip**: 4×4 grid
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

## MUX Membership in Topology Templates

The chip's topology template under `config/domain/topologies/` is the single source of MUX
membership. The chip pages, the schedulers, execution locks, and MUX result fan-out all read it
through `src/qdash/common/mux_mapping.py`, so a MUX label in the UI is the MUX the scheduler
targets. The top-level `muxes` key maps each MUX ID to its member qubits:

```yaml
qubits:
  0: {row: 0, col: 0}
  # ...
couplings:
  - [1, 0]
  # ...
muxes:
  0: [0, 1, 2, 3]
  1: [4, 5]
visualization:
  show_mux_boundaries: true
  region_size: 4
```

- The key is the MUX ID: the `mux` key of the matching `wiring.yaml` row, which keeps the MUX's
  hardware resources. The order in which MUXes are declared carries no meaning.
- The array index of a member is its local slot: the hardware assignment to the `i`-th port in
  that row's `ctrl` list. A slot is not a round: the ordering strategy maps it to a
  `parallel_by_round` round, and `CheckerboardOrderingStrategy` runs slot 2 of an odd MUX in
  round 0 (see [MUX Ordering Strategies](./one-qubit-ordering-strategies.md)). QDash never sorts a member
  list. Slot 0 is the representative qubit that runs MUX-level tasks.
- MUX IDs may be sparse, MUXes may have different sizes, and members need not be consecutive.
- A qubit in `qubits` that no MUX lists is **standalone** (not multiplexed). `muxes: {}` declares a
  chip whose qubits are all standalone, as the bundled `linear-16` and `heavy-hex-27` templates
  do. A standalone qubit is a valid calibration target, not a one-qubit MUX; a qubit that is not
  in `qubits` is unknown and rejected.
- `muxes` is required, so an empty declaration cannot be confused with a forgotten one. Loading
  also rejects a qubit in two MUXes or twice in one MUX, an empty member list, a member missing
  from `qubits`, negative or non-integer IDs, and qubit positions outside `grid_size`. A schedule
  fails when a member slot has no `ctrl` port in the wiring, or when a targeted MUX has no
  `wiring.yaml` row; it never drops that MUX's qubits. Chips without a topology keep skipping
  MUXes that the wiring does not list.
- `visualization.show_mux_boundaries` only decides whether the UI and the metrics PDF draw MUX
  outlines and labels. The UI draws each MUX around its members' positions; standalone qubits and
  cells without qubits get no MUX label. A zoomed region labels a MUX only when it shows one of
  its members, and a label over a single cell sits at the cell's bottom-left edge so it does not
  cover the cell's value.

The topology API (`GET /topology/{topology_id}`) returns the normalized `muxes`, the template
format it came from as `muxes_source`, `standalone_qubits`, and `mux_slots` (qubit ID to
hardware slot, excluding standalone qubits). The chip MUX API
(`GET /chips/{chip_id}/muxes`) lists declared MUXes only.

### Legacy Templates

Templates written before `muxes` declare a `mux:` block instead. The loader normalizes it into
`muxes`; a template that declares both `mux` and `muxes` is rejected as ambiguous.

| Legacy declaration | Normalized membership (`muxes_source`) |
| --- | --- |
| `mux: {enabled: false}` | No MUX: every qubit is standalone (`legacy_disabled`) |
| `mux: {enabled: true, groups: {0: {qids: [0, 1, 2, 3]}}}` | The listed groups (`legacy_groups`) |
| `mux: {enabled: true, size: 2}` without `groups` | MUX `qid // 4` on slot `qid % 4`, for the qubits the template defines (`legacy_qid_div_4`) |

Legacy slot gaps cannot be represented by canonical member arrays without changing slot
assignments. For example, legacy qubits `[0, 2]` occupy slots `0, 2`, although the API's
normalized `muxes` contains `{0: [0, 2]}`. Read `mux_slots` for the actual slots. Do not
export that array as canonical YAML: it would assign qubit 2 to slot 1. Keep the legacy
declaration until the hardware assignment can be migrated; API metadata is not template input.

A chip without `topology_id` keeps the `qid // 4` convention for any qubit. A chip whose
`topology_id` names a missing or invalid template does not fall back: scheduling fails, and the
execution lock claims the whole chip. `scripts/generate_topology.py` writes `muxes`.

### Scheduling Standalone Qubits

`wiring.yaml` maps only MUXes to hardware, so QDash does not know which modules a standalone
qubit shares. QDash schedules standalone qubits conservatively instead of inventing parallelism:

- The 1-qubit schedules run standalone qubits after every MUX stage, one at a time (a
  `STANDALONE` stage or one round per qubit). A run of only standalone qubits does not read the
  wiring.
- Manual rounds must list a standalone qubit, or a pair with one, alone in its round.
- The CR scheduler keeps pairs with a standalone qubit and gives each such pair its own group.
  A pair of two standalone qubits is never an intra-MUX pair.
- The execution lock reserves the whole chip for any target that includes a standalone qubit.
- MUX-level tasks, `BringUp`, and a `ConfigureAll` that derives its MUXes from qubit targets
  refuse standalone qubits with an error. They never pick a MUX for a qubit that has none.
- `MuxTargets` and `AllMuxTargets` select declared MUXes only. `AllQubitTargets` selects every
  known qubit, multiplexed or standalone.

### Qubex Backend Restriction

Qubex ignores the topology: it places qubit index `i` in MUX `i // 4` on control slot `i % 4`
and binds each `wiring.yaml` `ctrl` port to that qubit. The Qubex backend therefore accepts only
a topology where every qubit is in a MUX and MUX `N` lists a prefix of `[4N, 4N+1, 4N+2, 4N+3]`
in that order. The bundled templates with MUXes satisfy this. Other layouts, such as
`0: [4, 5, 6, 7]`, `0: [1, 0, 2, 3]`, or any standalone qubit (including a legacy
`mux: {enabled: false}` template), raise `MuxMappingError` naming each
offending MUX or qubit before any Qubex `Experiment` is built or connected:

- `CalibService` checks the chip's mapping before it takes a lock or creates an Execution.
- `QubexBackend.ensure_mux_mapping_compatible()` runs before `connect()` builds the
  `Experiment`, before the orchestrator writes calibration notes, and before `ConfigureAll`
  builds its own `Experiment`. The backend uses the mapping passed to it (`CalibConfig.mux_mapping`,
  `create_backend(..., mux_mapping=...)`), else `config["topology_id"]`, else the chip document
  for `config["project_id"]` and `config["chip_id"]`. With none of these it assumes the legacy
  layout and logs a warning.
- `POST /calibration-pipelines/validate` reports the mismatch as a `backend_name` problem.

The fake backend accepts any valid layout, including standalone and mixed targets. The check
lives in `check_qubex_mux_mapping()` in `src/qdash/common/mux_mapping.py`.

## Qubit ID to Coordinate Conversion

The CR scheduler's design-based direction inference (`qid_to_coords()` in
`src/qdash/workflow/engine/scheduler/cr_utils.py`) uses this conversion when the topology does
not declare `direction_convention: checkerboard_cr`. Topology templates list positions explicitly.

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

**16-qubit chip (4×4 grid):**

- Horizontal edges: 4 rows × 3 edges/row = 12 edges
- Vertical edges: 3 rows × 4 edges/row = 12 edges
- **Total: 24 nearest-neighbor edges**

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
Violation: Share qubit 1 (distance-0)

Pair A: 0-1
Pair B: 1-2
Violation: Adjacent via qubit 1 (distance-1)

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

## Topology Generation

### Available Script

1. **`scripts/generate_topology.py`**
   - Generates device topology configurations
   - Exports coupling graph data

### Usage

```bash
# Generate a 16-qubit square-lattice topology
uv run python scripts/generate_topology.py \
  --template square-lattice-mux \
  --size 16 \
  --output config/domain/topologies/square-lattice-mux-16.yaml
```

## References

- Wiring configuration: `config/qubex-config/{chip_id}/config/wiring.yaml`
- CR Scheduler implementation: `src/qdash/workflow/engine/scheduler/cr_scheduler.py`
- Topology generator: `scripts/generate_topology.py`
