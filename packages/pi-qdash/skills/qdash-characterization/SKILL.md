---
name: qdash-characterization
description: Plan and run new QDash measurements of qubit and coupling properties, from remeasuring one property of named qubits to the coherence_check, characterization, ef_calibration, and coherence_limit flow templates, covering T1, T2, Ramsey, noise spectroscopy, EF-transition calibration, thermal excitation, static ZZ, and gate coherence limits. Use when the user wants a property measured or measured again ("remeasure the T1 of Q0", "check coherence on MUX2"), not calibrated gates. Not for reporting stored values or trends, which need no new measurement.
license: Apache-2.0
---

# QDash Characterization

Characterization measures device properties: coherence, noise, the EF transition, readout
side effects, and coupling. Choose the smallest template that measures what the user needs, and
state which calibration parameters it also writes, because some characterization templates
calibrate pulses first.

Before planning or execution, load the `qdash` skill for the shared execution paths and
approval scope. In the hosted Agent, call `read_skill` with `name: "qdash"`; in pi CLI,
read the `qdash` skill file at the path supplied by skill discovery.

## Choose the template

| Goal | Template | Writes calibration |
| --- | --- | --- |
| Quick coherence health check of calibrated qubits | `coherence_check` | Rabi and coherence results; its Chevron is recorded without updating parameters |
| Gate fidelity limits from existing T1, T2, and gate durations | `coherence_limit` | Limit values only; it measures nothing new |
| EF transition and three-state readout | `ef_calibration` | GE Rabi and HPI, EF frequency and pulses, three-state classifier |
| Broad GE, EF, and coupling characterization in one run | `characterization` | Recalibrates GE pulses and the readout classifier before measuring |

All four accept `mux_ids` (with optional `exclude_qids`) or `qids`.

To measure one property again, such as the T1 of named qubits, a run of only that task is
usually smaller than any of these templates: the `simple` template with `qids` and that task.
Read the task's prerequisites with `qdash_get_pipeline_catalog` and the qubits' latest results
in the current cooldown first; the run must apply the configuration the task needs, and a qubit
without current pulses needs `qdash-one-qubit-calibration` before its coherence means much.

- `coherence_check` runs `Configure`, a `CheckChevron` that does not update parameters,
  `CheckRabi`, `CheckT1`, `CheckT2Echo`, and a short `CheckRamsey`, then reconfigures and runs a
  longer Ramsey with a smaller detuning. It assumes the qubits are calibrated; on uncalibrated
  qubits use `qdash-one-qubit-calibration` first.
- `coherence_limit` runs `Check1QGateCoherenceLimit`, generates a cross-resonance schedule, and
  runs `Check2QGateCoherenceLimit` on the scheduled couplings. The one-qubit limit reads the
  current `t1_average` and `t2_echo_average`, which `CheckT1Average` and `CheckT2EchoAverage`
  write (`full_calibration` and the GE stage of `characterization` run them; `coherence_check`
  does not). Confirm those values come from the current cooldown before reporting a limit.
- `ef_calibration` runs `ConfigureEF`, `CheckRabi`, `CreateHPIPulse`, `CheckAdaptiveEFChevron`,
  `CheckEFRabi`, `CreateEFHPIPulse`, `CreateEFPIPulse`, and `EFReadoutClassification` in one step,
  so the EF configuration and the measurements share one session. It needs an existing GE control
  frequency and readout frequency and amplitude, but not calibrated GE pulses.
  `configuration_mode` selects the `ge-ef-cr` (default) or `ge-ef-fh` control layout. Its
  docstring notes that `CheckEFRabi` lets Qubex choose the GE preparation pulse, so existing GE
  PI or DRAG pulses can take precedence over the HPI this flow calibrates.
- `characterization` configures the selected MUXes once with the layout the enabled stages
  need, calibrates GE pulses and readout, and keeps the qubits that succeeded. Then it runs the
  enabled stages: GE characterization (`run_ge_characterization`), EF calibration followed by EF
  characterization of EF-successful qubits (`run_ef_characterization`), and JAZZ coupling
  characterization (`run_coupling_characterization`). At least one stage must be enabled.

## Read partial results correctly

In `characterization`, calibration stages and measurement stages fail differently:

- A failed GE or EF calibration task stops that qubit's later calibration tasks, and the filter
  removes the qubit from dependent stages.
- A failed characterization measurement is recorded, and the qubit's remaining measurements still
  run. One failed measurement does not invalidate the qubit's other results.
- The coupling schedule is captured from GE-successful qubits before the EF stages, so EF failures
  do not remove pairs. JAZZ always measures static ZZ; it calculates coupling strength only when
  both qubits have calibrated anharmonicities in QDash.

Report results per qubit and per stage: measured, failed at a named task, or not run because a
calibration filter removed the qubit. Do not rerun the whole template for one failed
measurement. A short run of that task on that qubit tests it without recalibrating everything,
provided the run first applies the configuration layout the task needs.

## Retrieve and interpret

List templates with `qdash_query` action `flow_templates`, read one with action `flow_template`,
and check `qdash_list_flows` for a flow the user saved from it. Before running, read unfamiliar
tasks with `qdash_get_pipeline_catalog` and `taskNames`. Before interpreting a value or figure,
read the task with `qdash_get_task_knowledge`, and assign each result to its cooldown with
`qdash_list_cooldowns`. For coherence trends over time, follow the `qdash-timeseries-diagnosis`
skill.

A sharp coherence drop, suspected device anomaly, or repeated failure calls for reassessing
the evidence and task knowledge before repeating the measurement. A diagnostic repeat may be
appropriate within the approved scope and execution budget. Ask for human guidance when the
next step is unclear or requires expanding that scope.

## Running

Saved flows run with `qdash_execute_flow`; a template the user has not saved can be saved with
`qdash_save_flow` or reproduced as a pipeline, as the `qdash` skill describes. Both paths are
confirmation-gated, take the project execution lock, and write the results of completed tasks to
QDash directly. Before running `characterization` or `ef_calibration` on qubits calibrated for
other work, tell the user which parameters the run will replace.

Use a pipeline in place of a template only after checking that it preserves the template's
configuration, session boundaries, target selection, failure filtering, and coupling schedule
semantics. Validate the resulting spec with `qdash_plan_pipeline` before execution. If those
semantics cannot be represented, use the saved template flow.
