---
name: qdash-two-qubit-calibration
description: Plan, run, and diagnose QDash two-qubit (cross-resonance ZX90) calibration with the two_qubit, two_qubit_pairs, two_qubit_manual_rounds, full_calibration, and fast_full_calibration flow templates, from CR calibration through Bell-state checks and interleaved randomized benchmarking. Use when the user wants couplings or qubit pairs calibrated ("calibrate Q0 -> Q1", "calibrate this pair"), needs exact directed pairs run in the direction written, or asks why a completed coupling calibration has poor gate or Bell fidelity.
license: Apache-2.0
---

# QDash Two-Qubit Calibration

Two-qubit calibration builds a ZX90 gate for each directed (control, target) coupling and
validates it. Every template runs the same chain on each pair: `CheckCrossResonance`,
`CreateZX90`, `CheckZX90`, `CheckBellState`, `CheckBellStateTomography`,
`Check2QGateCoherenceLimit`, and `ZX90InterleavedRandomizedBenchmarking`
(`fast_full_calibration` omits the coherence limit). The templates differ in who chooses the
pairs, their direction, and their grouping.

Before planning or execution, load the `qdash` skill for the shared execution paths and
approval scope. In the hosted Agent, call `read_skill` with `name: "qdash"`; in pi CLI,
read the `qdash` skill file at the path supplied by skill discovery.

## Starting conditions

Both qubits of a pair need current single-qubit calibration in the same cooldown; the
`two_qubit` template expects candidate qubits that passed it. Check with `qdash_list_cooldowns`,
`qdash_target_report`, and `qdash_list_task_results`. Calibrate missing qubits first with
`qdash-one-qubit-calibration`, or use `full_calibration` to do both in one run. Use
`qdash_list_chip_couplings` for the chip's couplings and their directions.

## Choose the template by pair selection

| The user wants | Template |
| --- | --- |
| Exactly these directed pairs, grouped by QDash | `two_qubit_pairs` |
| These pairs in groups and an order they wrote | `two_qubit_manual_rounds` |
| Couplings among candidate qubits, chosen by QDash | `two_qubit` |
| Single-qubit and two-qubit calibration of whole MUXes | `full_calibration` or `fast_full_calibration` |
| A shorter, high-fidelity ZX90 searched adaptively on one directed pair | Ordinary pipelines guided by `qdash-zx90-optimization` |

- `two_qubit_pairs` takes `coupling_pairs`. The scheduler groups them for parallel runs and never
  adds, drops, or reverses a pair. A pair that is not a chip coupling in the written direction
  stops the run before any pair is calibrated.
- `two_qubit_manual_rounds` reads its rounds from the template source, so the user edits and
  saves a flow; the execution dialog offers no target override. QDash checks the rounds against
  the chip before any pair runs and never regroups them.
- `two_qubit` takes candidate `qids` and generates a cross-resonance schedule. Direction follows
  the chip's checkerboard pattern: forward by default, reverse with `inverse=true`. The schedule
  keeps one direction per coupling and can leave couplings out.
- `full_calibration` and `fast_full_calibration` take `mux_ids`, keep qubits that pass the
  single-qubit stages and the `x90_fidelity` threshold, and then schedule couplings among them
  the way `two_qubit` does.

When the user names pairs, do not substitute `two_qubit` or a schedule generated from their
qubits: the schedule may drop a pair or run it in the other direction. In a pipeline,
exact pairs need a `TwoQubitCalibration` step with `execution_mode` `manual` and the rounds the
user approved; an automatic step generates its own schedule. Running exact pairs with automatic
grouping needs a flow saved from `two_qubit_pairs`.

## Retrieve and prepare

List templates with `qdash_query` action `flow_templates`, read one with action `flow_template`,
and check `qdash_list_flows` for a flow the user saved from it. Read the chain's tasks with
`qdash_get_pipeline_catalog` and `taskNames` for prerequisites, and with
`qdash_get_task_knowledge` before interpreting any result or figure.

## Judge the result

After `qdash_wait_execution`, report each pair as validated, failed at a named task, or not
scheduled. A failed task stops that pair's later tasks; other pairs continue.

`completed` is an execution status. Judge quality from the outputs that task knowledge explains:
CR parameters and `zx_rotation_rate`, `zx90_gate_time`, `bell_state_fidelity`,
`two_qubit_gate_coherence_limit`, and `zx90_gate_fidelity` with its error. Use
`qdash_analyze_figure_json` before reading raw Plotly figures, and compare only with history from
the same cooldown.

## Diagnose poor quality

When a pair completed but its fidelity is poor, investigate read-only before rerunning anything.
Do not rerun randomized benchmarking first. Walk back through the chain from the latest
same-cooldown results: `CheckCrossResonance`, `CreateZX90`, `CheckZX90`, `CheckBellState`,
`CheckBellStateTomography`, and only then the benchmark. Compare the gate fidelity with its
coherence limit, and check the single-qubit state of both qubits; a degraded qubit can explain a
poor pair. Report the earliest step that looks wrong, the evidence, and the smallest rerun that
would test it, for example the chain for that one directed pair.

Reassess the evidence before repeating a failed step, especially when diagnostics disagree
or suggest a frequency collision or leakage. Continue only with an evidence-supported recovery
within the approved scope and execution budget. Ask for human guidance when the next step is
unclear or would exceed that scope.

## Running

Saved flows run with `qdash_execute_flow`; a pipeline follows the `qdash` skill. Both are
confirmation-gated, take the project execution lock, and write the results of completed tasks to
QDash directly. Agent calibration sessions target qubits only, so coupling calibration runs
through flows or pipelines.

Use a pipeline in place of a template only after checking that it preserves the template's
configuration, session boundaries, target selection, failure filtering, and coupling schedule
semantics. Validate the resulting spec with `qdash_plan_pipeline` before execution. If those
semantics cannot be represented, use the saved template flow.
