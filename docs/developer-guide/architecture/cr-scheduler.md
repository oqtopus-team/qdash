# CR Gate Scheduler

`CRScheduler` groups directed coupling pairs that can run together under QDash's modeled wiring
constraints. Groups execute sequentially; each pair runs its task list independently.

## Inputs and Output

The scheduler reads project-scoped chip couplings, calibration values, topology, and wiring.
`CRScheduleResult.parallel_groups` is a list of groups of `(control, target)` pairs.
Scheduling does not acquire hardware or execute measurements.

## Scheduling Pipeline

For qubit/MUX targets, `generate()` selects candidate couplings, chooses direction, checks
membership, and groups conflicts. Direction priority is topology `checkerboard_cr`, checkerboard
design when no measured frequencies exist, then measured frequency. The measured rule uses
`f_control < f_target`; `inverse` reverses the applicable direction.

## Conflict Graph and Groups

Pairs conflict when they share a qubit, a MUX, or MUX readout/control modules. A pair containing a
standalone qubit runs alone. Graph coloring forms groups, then `max_parallel_ops` caps their
size. Intra-MUX groups precede inter-MUX groups.

These are modeled resource checks, not a hardware guarantee or a graph-distance constraint.
Control modules are compared with control modules and readout with readout; read-in and pump
ports are not part of these checks. With QuEL-3 `<box ID>:<port>` wiring, module identity is the
whole box ID.

## Explicit Pairs

`schedule_pairs()` preserves the requested directions and pairs: it never adds, drops, or reverses
them. Empty, duplicate, unknown, or unmapped pairs fail. `CouplingTargets` uses this path; an
`inverse` request is invalid because directions are already explicit.

## Manual Rounds

A two-qubit step with `execution_mode="manual"` runs its checked `rounds` exactly as written.
It ignores an earlier CR schedule and rejects `max_parallel_ops`; split rounds yourself.
Shared validators check direction, topology, candidate membership, duplicates, and conflicts.
See [Manual Execution Rounds](../../user-guide/manual-execution-rounds.md).

## Workflow Integration

`GenerateCRSchedule` stores groups in `StepContext.metadata["cr_schedule"]`. A following automatic
two-qubit step reuses them. Later filters remove pairs with excluded qubits without regrouping.
Without a stored schedule, an automatic step generates one. Keep filters before schedule creation
when possible.

## Configurable Pipeline

`generate_with_plugins()` accepts `CRPairFilter` and `CRSchedulingStrategy` implementations.
Extensions must preserve scope, directed-pair validity, and hardware constraints, and report
metadata describing their choices.

## Source and Tests

Start with `src/qdash/workflow/engine/scheduler/cr_scheduler.py`, `cr_utils.py`, and `plugins/`
in the same directory. Run `uv run pytest tests/qdash/workflow/engine/scheduler/test_cr_scheduler.py`.
Manual-round changes also require the common and workflow manual-round tests.
