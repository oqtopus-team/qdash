# 1-Qubit Calibration Scheduler

`OneQubitScheduler` orders qubit or MUX targets using the chip's topology and wiring. It produces
an order; execution and hardware reservations belong to the workflow service.

## Wiring Model

MUX membership comes from the [topology](./square-lattice-topology.md). Wiring classifies MUXes
as A, B, or MIXED. Stages run in that order; MIXED MUXes sharing a recognized Box B control
module go into separate stages. Standalone qubits run last, one at a time.

Classification reads channel names, not `box.yaml`. Names such as `R21B-5` identify Box B;
`<box ID>:<port>` names do not identify A/B, so those MUXes are MIXED. Without recognized Box B
control names, this scheduler does not detect shared-box conflicts. Use the
[hardware guidance](../../user-guide/setup/qubex-backend.md#check-parallel-execution-on-quel-3).

## Schedule Forms

| Method | Result |
| --- | --- |
| `generate()` | Sequential stages of parallel MUX groups |
| `generate_rounds()` | Sequential rounds, at most one qubit per MUX |
| `generate_simultaneous_spectroscopy_batches()` | Batches for a supported simultaneous operation |

The `*_from_mux()` forms expand MUX targets and apply exclusions. Spectroscopy batches report
box classification but do not split on A/B conflicts; the caller must support the batch.

## Execution Modes

| Mode | Waiting rule |
| --- | --- |
| `parallel_by_mux` | Each MUX starts its next qubit when ready |
| `parallel_by_round` | All qubits finish before the next round |
| `sequential` | One qubit at a time |
| `simultaneous_spectroscopy` | Each supported call measures a batch |

Except spectroscopy, a target runs its entire call list independently. Parallel modes do not
synchronize pulses. Templates and `BringUp` default to `parallel_by_mux`; direct one-qubit
steps default to `parallel_by_round`. Worker-pool capacity does not establish hardware capacity.

## Manual Rounds

Manual steps bypass scheduling but share validation in `src/qdash/common/manual_rounds.py`.
Rounds must cover exactly the current targets, without duplicates, and respect topology,
MUX, stage, and recognized shared-module constraints. A standalone qubit runs alone.
The API preview, pipeline preflight, and worker must enforce the same rules. See
[Manual Execution Rounds](../../user-guide/manual-execution-rounds.md).

## Invariants and Failure Behavior

Empty targets fail. An explicit topology must resolve; unknown qubits or unwired MUX members
fail instead of falling back to arithmetic. Legacy chips without topology keep their older
mapping behavior. Keep stage and target ordering deterministic.

### Migrate from the former names

Use `execution_mode` instead of `mode`; replace `serial`, `scheduled`, and `synchronized` with
`sequential`, `parallel_by_mux`, and `parallel_by_round`. Old names are rejected, not aliased.
Round APIs use `generate_rounds`, `OneQubitRoundScheduleResult`, and `OneQubitRound`.

## Source and Tests

The scheduler and ordering contracts live under `src/qdash/workflow/engine/scheduler/`.
`src/qdash/workflow/service/strategy.py` maps modes to execution strategies.

Run `uv run pytest tests/qdash/workflow/engine/scheduler/test_one_qubit_scheduler.py` and the
ordering tests after scheduling changes. Manual-round changes also need
`tests/qdash/common/test_manual_rounds.py` and the workflow manual-round tests.
