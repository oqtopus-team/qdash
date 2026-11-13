# Square Lattice Topology

QDash supports superconducting quantum processors with square lattice topology, where qubits are arranged in a 2D grid with nearest-neighbor coupling.

## Topology Model

### Supported Chip Sizes

| Qubits | Grid | MUX grid | Nearest-neighbor edges |
| --- | --- | --- | --- |
| 16 | 4×4 | 2×2 | 24 |
| 64 (64Qv3) | 8×8 | 4×4 | 112 |
| 144 (144Qv2) | 12×12 | 6×6 | 264 |

An N×N grid has `2N(N−1)` undirected nearest-neighbor edges.

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

The standard layout assigns qubits `4N` through `4N+3` to MUX `N`, with MUXes in row-major order.

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

The same 2×2 MUX layout extends to a 6×6 grid of MUXes.

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
| --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 (TL) | (0, 0) | (0, 0) | (0, 0) |
| 1 | 0 | 1 (TR) | (0, 0) | (0, 1) | (0, 1) |
| 2 | 0 | 2 (BL) | (0, 0) | (1, 0) | (1, 0) |
| 3 | 0 | 3 (BR) | (0, 0) | (1, 1) | (1, 1) |
| 4 | 1 | 0 (TL) | (0, 1) | (0, 0) | (0, 2) |
| 16 | 4 | 0 (TL) | (1, 0) | (0, 0) | (2, 0) |
| 17 | 4 | 1 (TR) | (1, 0) | (0, 1) | (2, 1) |

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
   - Example: 1-4 (MUX 0 → MUX 1), 2-16 (MUX 0 → MUX 4)
   - Slower execution due to cross-MUX communication

### Total Edge Counts

See [Supported Chip Sizes](#supported-chip-sizes) for counts before direction selection.

## MUX Resource Conflicts

The CR scheduler separates pairs that share a qubit, MUX, or readout/control module. A pair
containing a standalone qubit runs alone. Module identity comes from `wiring.yaml`; the exact
checks and their limits are in [Conflict Graph and Groups](./cr-scheduler.md#conflict-graph-and-groups).

## CR Gate Constraints

### Frequency Directionality

The scheduler selects direction from the topology convention, checkerboard design, or measured
frequencies, in that priority order. The measured-frequency rule uses `f_control < f_target`;
`inverse=True` reverses the applicable direction. See
[Scheduling Pipeline](./cr-scheduler.md#scheduling-pipeline).

### Distance-2 Constraint

The current scheduler checks shared qubits and hardware resources, not graph-hop distance.
Geometric separation alone does not establish that two pairs can run together.

## Coordinate System

### Row and Column Indexing

- **Row index**: 0 (top) to N-1 (bottom)
- **Column index**: 0 (left) to N-1 (right)
- **Origin**: Top-left corner (0, 0)

### Edge Naming Convention

Coupling IDs use `control-target`, such as `0-1`; reversing the order selects the other
direction. Coordinate rows and columns both start at the top-left.

## Topology Generation

`scripts/generate_topology.py` generates topology configurations and their coupling graph.

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
