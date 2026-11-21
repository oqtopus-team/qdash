---
name: qdash-one-qubit-calibration
description: Plan, run, and recover single-qubit QDash calibration with the coarse_one, fine_one, one_qubit, fast_full_calibration, full_calibration, and simple flow templates, from readout search and pulse calibration through randomized benchmarking. Use when the user wants qubits calibrated or recalibrated, wants a failed single-qubit stage recovered, or asks which single-qubit flow fits the chip's state. Not for first-time spectroscopy (qdash-chip-bringup) or two-qubit gates (qdash-two-qubit-calibration).
license: Apache-2.0
---

# QDash Single-Qubit Calibration

Single-qubit calibration turns bring-up estimates or an earlier calibration into checked pulses,
a readout classifier, and benchmarked gate fidelities. Task definitions describe each
measurement; this skill chooses the flow template and decides when a qubit may move on.

Before planning or execution, load the `qdash` skill for the shared execution paths and
approval scope. In the hosted Agent, call `read_skill` with `name: "qdash"`; in pi CLI,
read the `qdash` skill file at the path supplied by skill discovery.

## Choose the template from the chip's state

Establish the state first: `qdash_list_cooldowns` for the current cooldown, then
`qdash_target_report`, `qdash_list_task_results`, or `qdash_get_chip_metrics` for the latest
results of the selected qubits in that cooldown.

| State of the selected qubits | Template |
| --- | --- |
| Bring-up just finished; no pulses yet | `coarse_one`, or `one_qubit` to continue into the fine stage |
| Coarse pulses exist; fidelity or readout needs work | `fine_one` |
| Calibrated earlier in the cooldown; routine full pass | `one_qubit`, or `fast_full_calibration` when the chip is close to calibrated and two-qubit work follows |
| One or a few tasks to repeat for named qubits | `simple` with an explicit task list |

- `coarse_one`: `Configure`, `CheckCoarseReadoutParams`, `Configure`, two `CheckRabi` calls,
  create and check HPI, PI, DRAG HPI, and DRAG PI, then `CheckT1`, `CheckT2Echo`, and
  `CheckRamsey`. It needs a qubit frequency, control amplitude, and readout settings, which
  bring-up provides.
- `fine_one`: after coarse calibration, two rounds of pulse calibration with readout amplitude
  and frequency optimization and `Configure` between them, a final pulse calibration, then
  `ReadoutClassification`, `RandomizedBenchmarking`, and `X90InterleavedRandomizedBenchmarking`.
- `one_qubit`: the `coarse_one` stage, `FilterByStatus`, then the `fine_one` stage. Only
  qubits whose coarse stage succeeded enter the fine stage, and each stage records its own
  execution. `check_only=true` runs the coarse stage alone.
- `full_calibration` and `fast_full_calibration`: `ConfigureAll`, a one-qubit check stage,
  `FilterByStatus`, a fine-tune stage, `FilterByMetric` on `x90_fidelity`, then two-qubit
  calibration of the scheduled couplings. They accept only `mux_ids`. `fast_full_calibration`
  shortens the check stage and skips the averaged T1 and T2 measurements. Choose them only when
  two-qubit calibration is part of the goal; see `qdash-two-qubit-calibration` for that part.

Every template except the full calibrations accepts `mux_ids` (with optional `exclude_qids`) or
`qids`; prefer `mux_ids` for more than a few qubits and `qids` to recover named qubits.

## Retrieve and prepare

List templates with `qdash_query` action `flow_templates` and read one with action
`flow_template`. Check `qdash_list_flows` for a flow the user saved from the template. Before
editing a task list or recovering a failure, read the tasks with `qdash_get_pipeline_catalog` and
`taskNames` for their purpose and prerequisites, and with `qdash_get_task_knowledge` for expected
results and failure modes.

## Move on, recover, or stop

After `qdash_wait_execution`, summarize passed and failed qubits per stage, and fetch the figures
of failed tasks with `qdash_get_task_figures`.

- A qubit moves on when every task of the stage completed and the task knowledge accepts its
  outputs. `completed` is an execution status, not a quality verdict.
- A failed task stops that qubit's later tasks in the stage. Parameters from the tasks before the
  failure are already written. Other qubits continue.
- A qubit that failed the coarse stage does not enter the fine stage of `one_qubit`; do not run
  `fine_one` on it as a workaround. Diagnose the failed task from its result, figures, and task
  knowledge. When the stage's first readout or Rabi tasks fail, the inputs from bring-up may be
  wrong; consider `qdash-chip-bringup` for its MUX. Rerun the coarse stage for that qubit with
  `qids` once the cause is addressed.
- Repeated failures, disagreeing diagnostics, or suspected device anomalies call for
  reassessing the evidence and task knowledge before another attempt. Continue a supported
  recovery within the approved scope and execution budget; ask for human guidance when the
  cause or next step remains unclear, or a change would exceed that scope.

Report each qubit as calibrated, failed at a named task and stage, or filtered out, with the
key outputs (for example `x90_fidelity`) and execution links.

## Running

Saved flows run with `qdash_execute_flow`; a template the user has not saved can be saved with
`qdash_save_flow` or reproduced as a pipeline with the template's step and task lists, as the
`qdash` skill describes. Both paths are confirmation-gated and write the results of completed
tasks to QDash directly. A bounded, candidate-gated recovery of one qubit uses an agent
calibration session instead; see the `qdash` skill. Do not use a flow or pipeline to repeat what
an agent session refused, rejected, or stopped on.

Use a pipeline in place of a template only after checking that it preserves the template's
configuration, session boundaries, target selection, failure filtering, and coupling schedule
semantics. Validate the resulting spec with `qdash_plan_pipeline` before execution. If those
semantics cannot be represented, use the saved template flow.
