# Square Lattice Topology

Topology templates define qubit positions, couplings, and MUX membership for chip views,
scheduling, resource locks, and result fan-out.

## Topology Model

The square layout uses nearest-neighbor couplings and four-qubit, 2×2 MUX blocks.

### Supported Chip Sizes

| Qubits | Grid | Undirected nearest-neighbor edges |
| --- | --- | --- |
| 16 | 4×4 | 24 |
| 64 | 8×8 | 112 |
| 144 | 12×12 | 264 |

Rows and columns start at the top-left. Coupling IDs are directed: `0-1` and `1-0` differ.

## MUX Membership in Topology Templates

`config/domain/topologies/` is the source of truth. A template's `muxes` maps MUX IDs to ordered
member qubits; that order selects control-port slots in `wiring.yaml`. Use
`src/qdash/common/mux_mapping.py` everywhere instead of repeating arithmetic.

A known qubit absent from every MUX is standalone. An unknown qubit is invalid. A declared topology
that cannot load raises `MuxMappingError`; do not schedule from a guessed layout. Missing project
context, an unknown chip, or a chip without topology uses the legacy MUX `qid // 4`, slot `qid % 4`
mapping. This fallback is not verification of physical wiring.

### Legacy Templates

The loader normalizes legacy `mux:` declarations. A template with both `mux` and `muxes` is
ambiguous and rejected. `mux: {enabled: false}` makes every qubit standalone.

### Scheduling Standalone Qubits

Standalone hardware sharing is unknown, so one-qubit scheduling runs them individually after
MUX stages. A two-qubit pair containing one runs alone. Resource locks conservatively reserve
the whole chip when needed.

### Qubex Backend Restriction

Qubex requires every qubit to belong to the conventional MUX and slot: MUX `N` lists a prefix of
`[4N, 4N+1, 4N+2, 4N+3]` in order. Reordered, remapped, or standalone layouts are rejected before
connecting hardware, even though the generic topology model can represent them.

## CR Gate Constraints

Topology direction conventions take priority over inferred design or frequency direction.
[CR Scheduler](./cr-scheduler.md) describes direction and conflict checks. Geometric distance alone
does not prove that pairs can execute together.

## Topology Generation

`scripts/generate_topology.py` generates square templates and coupling graphs. Inspect its CLI
help before generating a new size, then validate membership and backend compatibility.

Test changes in the common topology/MUX tests and both scheduler suites. Keep UI, execution locks,
and backend configuration on the same mapping contract.
