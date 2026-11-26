---
name: qdash-chip-bringup
description: Plan and run first-time QDash bring-up of MUXes with the box_setup, bringup, and check_waveform flow templates, from capture delay correction through resonator and qubit spectroscopy to a first qubit frequency. Use when the user wants a new chip, a new cooldown, or MUXes brought up ("bring up MUX0"), or their readout or qubit frequencies are not yet known; the skill checks the current state first. Not for chips that already have calibrated pulses; use qdash-one-qubit-calibration for those.
license: Apache-2.0
---

# QDash Chip Bring-up

Bring-up finds what later calibration assumes: a capture window that contains the readout
pulse, a readout frequency and amplitude for each resonator, and a coarse qubit frequency and
control amplitude for each qubit. The goal is reached when every selected qubit has those
values and can enter the coarse stage of `qdash-one-qubit-calibration`.

Before planning or execution, load the `qdash` skill for the shared execution paths and
approval scope. In the hosted Agent, call `read_skill` with `name: "qdash"`; in pi CLI,
read the `qdash` skill file at the path supplied by skill discovery.

## Decide whether bring-up applies

Start from the chip's state, not the user's wording. Use `qdash_list_cooldowns` and
`qdash_list_cooldown_wiring_events` to see whether the cooldown or wiring is new, and
`qdash_get_chip_metrics` or `qdash_list_task_results` to see whether the selected qubits already
have readout and qubit frequencies from the current cooldown.

- Missing or no longer valid readout or qubit frequencies: select the bring-up procedures
  needed to establish them. A new cooldown or wiring change calls for reassessing capture delay,
  readout settings, and frequency validity; it does not by itself require every procedure.
- Values exist and coarse calibration ran recently: skip bring-up and use
  `qdash-one-qubit-calibration` instead. Re-running bring-up replaces working values with
  spectroscopy estimates.
- Only some qubits lack values: run bring-up for their MUXes, not for the whole chip.

## Retrieve the templates

List the templates with `qdash_query` action `flow_templates`, and read one with action
`flow_template` and its `templateId`. Check `qdash_list_flows` for a flow the user already saved
from a template; run that flow when it matches the plan. Read each task's purpose and
prerequisites with `qdash_get_pipeline_catalog` and `taskNames`, and its physics, expected
figures, and failure modes with `qdash_get_task_knowledge`.

Available procedures and their ordering conditions:

1. `box_setup` runs `CorrectCaptureDelay` once per MUX. It uses a fixed readout tone, so it
   needs no readout calibration, and it writes the capture delay files that later sessions
   reload. QuEL-1 and QuEL-3 are supported. Run it first when the capture delay is unknown or
   the readout boxes changed.
2. `bringup` runs `CheckResonatorSpectroscopy` once per MUX on the representative qubit,
   then `CheckQubitSpectroscopy`, `CheckControlAmplitude`, and `CheckAdaptiveChevron` for each
   qubit. It does not reconfigure hardware between tasks; the next flow's `Configure` applies the
   new values.
3. `check_waveform` runs `CheckWaveform` to inspect the captured readout waveform. Use it to
   confirm the capture window after `box_setup`, or when readout looks wrong.

`box_setup` and `bringup` require `mux_ids` and ignore `qids`; `exclude_qids` removes qubits
from the selected MUXes. `check_waveform` accepts either `mux_ids` or `qids`. The resonator
assignment order within a MUX can differ between chip designs; the `bringup` template's code
explains when to override it, so read it before a chip type runs for the first time.

## Move on or stop

After each run, use `qdash_wait_execution`, then inspect failed tasks with
`qdash_get_task_result` and `qdash_get_task_figures`.

- Move on to the next template, and finally to the coarse stage, only for qubits whose tasks
  completed with values that the task knowledge accepts.
- When `CheckResonatorSpectroscopy` fails for a MUX, its qubits have no readout basis. Report it
  and do not continue that MUX into qubit spectroscopy or coarse calibration.
- When the spectroscopy or Chevron of a qubit fails, report the qubit with its figures and
  continue the other qubits. Inspect evidence and task knowledge before proposing a changed
  range. Wiring, attenuation, and frequency assignment are possible causes; use
  `qdash_get_cooldown_wiring` when relevant. Retry only within the approved scope and bounds,
  and request guidance when the evidence does not support a next step.

Report each MUX and qubit as ready, failed at a named task, or not run, with execution links.

## Triage, offline reanalysis, and recovery

Triage spectroscopy results from their outputs before spending evaluations or hardware time.

1. Fast path: a qubit whose tasks completed with `f01_quality_level` of 3 or more, an
   `optimal_power` below -10 dB, a `coarse_control_amplitude` below 0.8, and no downstream
   failure is clean. Move it on without calling `qcal_evaluate`.
2. Inspect the rest: a failed spectroscopy, `f01_quality_level <= 2`, `optimal_power >= -10 dB`,
   `coarse_control_amplitude >= 0.8`, or a failure in `CheckControlAmplitude` or
   `CheckAdaptiveChevron`. Fetch the spectroscopy figure (`qdash_get_task_figures` or
   `qdash_build_qcal_evidence`) and evaluate it with `qcal_evaluate`; for these 2D heatmaps
   prefer `use_examples: false`.
3. Reanalyze offline when the evaluation reports `UNSUPPORTED_F01_MARKER` or
   `FALSE_OR_MISASSIGNED_PEAK` and the figure shows a real feature: call
   `qdash_reanalyze_qubit_spectroscopy` or `qdash_reanalyze_resonator_spectroscopy` with the
   result's `sourceTaskId` and adjusted `parameters` (for example `f01_height_min`, `top_power`,
   or the binarization thresholds for f01; the power region, `bare_shift_estimator_type`, or
   `resonator_assignment_order` for resonators). Evaluate the returned figure with
   `qcal_evaluate` again, and change one or two parameters per attempt. Stop after a few attempts
   and measure again, or request guidance, when no setting marks the feature.
4. Confirm a verified candidate on hardware with a targeted Stored Plan before relying on it.
   Build a short spec, store it with `qdash_create_pipeline_plan`, and run it with a direct
   `qdash_run_pipeline` call and its `planId`:
   - A reanalyzed qubit: `CheckControlAmplitude` with
     `input: {"control_frequency": <coarse_qubit_frequency>, "coarse_control_amplitude": <coarse_control_amplitude>}`,
     then `CheckAdaptiveChevron`, which refines and stores `qubit_frequency`.
   - A reanalyzed resonator: `CheckQubitSpectroscopy` with
     `input: {"readout_frequency": <readout_frequency>, "readout_amplitude": <readout_amplitude>}`.

   Reanalysis writes nothing; only the confirming run's completed tasks store values. Report
   which values came from reanalysis and which run confirmed them.

## Running

Saved flows run with `qdash_execute_flow`; a template the user has not saved can be saved with
`qdash_save_flow` or reproduced as a pipeline as the `qdash` skill describes. Both paths are
confirmation-gated, take the project execution lock, and write the results of completed tasks to
QDash directly, including for qubits whose later tasks fail. Run a sequence the user approved
template by template, and inspect each result before starting the next.

Use a pipeline in place of a template only after checking that it preserves the template's
configuration, session boundaries, target selection, failure filtering, and coupling schedule
semantics. Validate the resulting spec with `qdash_plan_pipeline` before execution. If those
semantics cannot be represented, use the saved template flow.
