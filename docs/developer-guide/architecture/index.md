# Architecture Deep Dives

These pages explain cross-component designs whose invariants are not owned by only the API, UI,
or workflow subsystem.

## Choose a Design

| Design | Use it to understand |
| --- | --- |
| [Square Lattice Topology](./square-lattice-topology.md) | Qubit coordinates, couplings, MUX organization, and resource conflicts. |
| [Provenance](./provenance.md) | Parameter history, lineage traversal, impact analysis, and persistence. |
| [Notes](./notes.md) | Scoped summaries, result notes, audit events, and note search. |
| [1-Qubit Scheduler](./one-qubit-scheduler.md) | Wiring-aware grouping and stage generation for single-qubit calibration. |
| [1-Qubit Ordering Strategies](./one-qubit-ordering-strategies.md) | Ordering strategies and synchronized scheduling inside 1-qubit groups. |
| [CR Gate Scheduler](./cr-scheduler.md) | Conflict detection and graph coloring for two-qubit calibration. |

The [Workflow Development](../workflow/index.md) section explains the engine that consumes these
designs. Follow the [Documentation Guidelines](../docs-guidelines.md) when adding another deep
dive.
