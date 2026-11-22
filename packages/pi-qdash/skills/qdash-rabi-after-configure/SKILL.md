---
name: qdash-rabi-after-configure
description: Keep the Rabi normalization of T1, T2 echo, Ramsey, and other Rabi-normalized single-qubit tasks fresh after Configure or ConfigureAll. Use when planning, reviewing, or recovering a QDash flow, pipeline, or agent session that reconfigures qubits and then measures them ("Configure then T1, T2 echo, and Ramsey on Q6"), or when T1 or T2 echo fits are flat, low in R², or out of range after a Configure. Checks that a CheckRabi on the same qubits ran after the latest Configure and traces the rabi_* inputs of suspect results. Not for choosing a calibration or characterization template.
license: Apache-2.0
---

# QDash Rabi After Configure

`Configure` and `ConfigureAll` reload and send the hardware configuration, which can change the
IQ rotation and offset of a qubit's readout. Tasks such as `CheckT1`, `CheckT2Echo`, and
`CheckRamsey` project their signal with the Rabi normalization stored by the last `CheckRabi`
(`rabi_amplitude`, `rabi_offset`, `rabi_angle`, `rabi_reference_phase`, and the rest of that
group). Normalization measured before the latest Configure projects the new signal on old
coordinates, and the fit can fail or report a wrong value without any error.

This skill is guidance for the model. QDash does not enforce it: a task checks only that the
stored `rabi_r2` passes its threshold and that the readout duration matches, and
`qdash_plan_pipeline` checks only that Rabi parameters exist with a matching readout duration.
Neither looks at when they were measured relative to a Configure, so a valid plan and a
`completed` execution do not show that the normalization is fresh.

Load the `qdash` skill for execution paths and approval scope, and the skill that chose the
sequence (`qdash-one-qubit-calibration`, `qdash-characterization`, or
`qdash-agent-calibration`). In the hosted Agent, call `read_skill` with each name; in pi CLI,
read the skill files at the paths supplied by skill discovery.

## The rule

For each target qubit, every Rabi-normalized task must read Rabi parameters from a `CheckRabi`
on that qubit that ran after the most recent Configure event for it and wrote its outputs to the
calibration state.

- Rabi-normalized tasks are those whose inputs include the Rabi normalization group in
  `qdash_get_pipeline_catalog` with `taskNames`. Besides the three coherence tasks this covers
  the averaged coherence tasks, HPI, PI, and DRAG pulse tasks, randomized benchmarking, and
  several noise measurements; read the catalog rather than relying on this list.
- A Configure event is an explicit `Configure` call, a `ConfigureAll` that covers the qubit's
  MUX, a step with `configure: true`, an agent session step with `reconfigure: true`, or a
  template stage that configures.
- A `CheckRabi` before that event never substitutes, even from the same day or the same
  execution. A later Configure event invalidates the normalization again.
- A `CheckRabi` call with `update_calibration_parameters: false`, or an agent session candidate
  that was not committed, leaves the old values in place for the next task.

The smallest calibrated single-qubit sequence that follows the rule:

```json
[
  {"name": "Configure", "on_failure": "stop"},
  {"name": "CheckRabi", "on_failure": "stop"},
  {"name": "CheckT1"},
  {"name": "CheckT2Echo"},
  {"name": "CheckRamsey"}
]
```

`on_failure: "stop"` keeps a qubit whose Configure or Rabi failed from measuring coherence on
stale normalization; other qubits continue. Add a fresh `CheckRabi` after any further Configure
in the same step, as `coherence_check` does before its long Ramsey.

## Review a planned or stored sequence

Read the sequence first: a flow template with `qdash_query` action `flow_template`, a saved flow
with `qdash_get_flow`, or a pipeline with the calls `qdash_plan_pipeline` resolves. Walk each
qubit's calls in order, mark the Configure events, and check that a persisting `CheckRabi`
follows the last event before each Rabi-normalized call. Fix a gap by inserting `CheckRabi` with
`on_failure: "stop"` right after the Configure, then plan again. The current `coherence_check`,
`coarse_one`, `fine_one`, `one_qubit`, `full_calibration`, and `fast_full_calibration` templates
already follow the rule; keep that order when editing them or composing a pipeline from them.

- A stored flow runs `Configure`, `CheckT1`, `CheckT2Echo`, `CheckRamsey`: Rabi is missing.
  Insert `CheckRabi` after `Configure` before proposing the run.
- A sequence runs `Configure`, `CheckRabi`, `CheckT1`, `Configure`, `CheckRamsey`: the second
  Configure invalidates the first Rabi. Insert `CheckRabi` after the second Configure.
- An agent session must reconfigure, but `CheckRabi` is outside its allowed tasks, or its action
  budget has no room for it: do not run the coherence step on stale normalization. Explain the
  gap and ask the user to approve a session that covers it. Do not stretch the session, create a
  session or flow to get around it, or treat an expert's guidance as that approval.

In an agent session a step reads the committed calibration state. Run `CheckRabi` with
`reconfigure: true`, which needs `allow_reconfigure`, so Configure and Rabi share one execution
in that order. Commit the Rabi outputs the next tasks read before running them, under the
session's `parameter_updates` grant with `qdash_commit_agent_session_update` or with a per-call
commit, and run the coherence steps without `reconfigure`. When proposing the session, include
`CheckRabi` in its tasks, its Rabi outputs in `parameter_updates`, and room in `max_actions`.

## Diagnose a suspect coherence result

Suspect stale normalization when a Rabi-normalized task ran after a Configure and the T1 or T2
echo fit has a low R² although a decay is visible, the normalized signal is inverted or outside
its expected range, or the fit is flat. `CheckRamsey` can still complete and write `t2_star` and
`qubit_frequency`, so a completed Ramsey does not show the normalization was fresh.

1. Read the consuming result with `qdash_get_task_result`. Each Rabi input records the
   `task_id`, `execution_id`, and `calibrated_at` of the `CheckRabi` that produced it.
2. Find the latest Configure event for that qubit before the consuming task with
   `qdash_list_task_results` (`taskName` `Configure` or `ConfigureAll`, `qid`, and `executionId`
   when it ran in the same execution), and read the source `CheckRabi` the same way.
3. Compare the `start_at` and `end_at` times. A source `CheckRabi` that ended before the latest
   Configure started is stale. A shared date proves nothing, and a shared execution ID does not
   order calls inside one execution.

Recover with a fresh `CheckRabi` after Configure on the same qubit, then remeasure within the
approved scope. Do not relax a threshold, refit the old data, or accept the stale result. A
flow or pipeline already wrote the outputs of its completed tasks: report which values came from
stale normalization and let the user decide what to remeasure. In an agent session a failed or
uncertain `CheckRabi` or coherence result goes to an expert with `qdash_request_agent_human`, as
the `qdash-agent-calibration` skill describes. Evaluate with `qcal_evaluate` only when the
session's evaluation mode or the user asks for it.

A user-reported case illustrates the failure; its numbers are not thresholds. On one qubit, an
execution reconfigured and then ran T1, T2 echo, and Ramsey with Rabi parameters from an earlier
execution. T1 and T2 echo fits had R² near zero, while Ramsey completed and wrote `t2_star` and
`qubit_frequency`. A rerun with `CheckRabi` between Configure and the coherence tasks measured a
substantially different `rabi_angle` and gave usable T1, T2 echo, and Ramsey fits.
