---
name: qdash-zx90-optimization
description: Search, within a user-approved hardware time budget and parameter bounds, for a shorter ZX90 gate with high fidelity on one directed coupling, choosing each small CheckCrossResonance condition change from the last result, recording every experiment and decision in one QDash calibration session's audit, and confirming the best candidate against the incumbent with ordinary QDash pipelines. Use when the user asks to shorten or optimize the ZX90 or CR gate of one pair ("make the Q0 to Q1 ZX90 shorter without losing fidelity", "tune the CR conditions of this pair adaptively"), or to design an agent-versus-fixed-procedure comparison of such searches. Not for calibrating pairs (qdash-two-qubit-calibration).
license: Apache-2.0
---

# QDash ZX90 Optimization

You run an adaptive search on one directed pair while the chat is open: each experiment
changes one `CheckCrossResonance` condition inside bounds the user approved, you read its
evidence, report it, and choose the next experiment. One QDash calibration session holds the
whole search: every pipeline run is recorded in it, and each experiment, reading, and the final
conclusion is a decision in its audit, so the search can be resumed and reviewed from QDash. QDash tasks own the measurements and the
quality calculations (tomography fits, amplitude fit, benchmark fit, coherence limit); you own
the interpretation and the next decision. A shorter gate is a screening criterion; benchmarked
fidelity is the objective.

Load the `qdash` skill first for execution paths and approval scope, and use
`qdash-two-qubit-calibration` for the chain, its outputs, and diagnosis of a poor pair.

## What exists and what does not

| Available | Not available |
| --- | --- |
| `qdash_plan_pipeline` and `qdash_run_pipeline` with a `CustomTwoQubit` step in `manual` mode for the one pair | A QDash optimizer, flow, or scheduler that runs this search; anything that acts after your turn ends or the runtime stops |
| `CheckCrossResonance` run keys `adiabatic_safe_factor`, `max_amplitude`, `max_time_range` as the search keys | qubex arguments QDash does not pass: CheckCR `cr_amplitude`, `time_range`, `n_iterations`, `tolerance`; CreateZX90 `initial_state`, `degree`, `n_repetitions`, `duration_unit` |
| Other CR controls this search leaves unset: CheckCR `ramptime`; CreateZX90 `duration`, `ramptime`, `amplitude_range`, `adiabatic_safe_factor`, `max_amplitude`, `rotary_multiple`, `duration_buffer` | A search over those controls; it needs its own approved scope and design |
| `qdash_wait_execution`, `qdash_get_execution`, `qdash_list_executions`, task results, figures, task knowledge | A tool that cancels an execution; restoring an earlier pair state; saving a candidate without making it the current calibration |
| `ZX90InterleavedRandomizedBenchmarking` per arm | Paired multi-arm IRB and its paired statistics; agent sessions on couplings (agent sessions target qubits) |
| A calibration session for the search: `qdash_create_calibration_session`, `qdash_list_calibration_sessions`, `qdash_get_calibration_session`, `qdash_record_calibration_decision`, `qdash_get_calibration_session_audit` | Any authority from it: it groups coupling pipelines and records history, and grants no run, bound, or budget |

Stop and report the gap when the request needs an item in the right column. If a run is
refused (an HTTP 409, a held execution lock, a paused agent session), report it; do not retry
through another path.

## Authorization and approval

Before the first run, hold one scope record, taken from approved device or session constraints
the user or operator already gave, and ask only for what is missing:

- the directed pair and the cooldown;
- for each key you may change: initial value and min, max, and step, or an explicit candidate
  set, with its source (device constraint, operator, or session);
- the approved control-amplitude bound B for this pair and its source (see the scan check);
- the total hardware-time budget, the reserve for the final comparison, the repeat cap per
  condition (for example 2), and each stage's `shots` and benchmark `n_trials`;
- the acknowledgement that completed tasks overwrite the pair's calibration;
- the status cadence for long waits (default 10 minutes).

The defaults in the parameter table are code defaults, not certified bounds. Never invent a
step, a threshold, or a wider bound, and never extend the bounds or the budget yourself. A
larger budget or range is a new authorization the user gives explicitly; running out of budget
and stopping is the intended end, not a failure.

Each `qdash_run_pipeline` is a reviewed write. In the QDash web Agent the call ends your turn
with an approval card showing the exact spec; the runtime runs it only when the user approves
and then starts your next turn with the outcome. The pi CLI shows a confirmation dialog. The
approved scope does not replace that approval; it means you call the tool directly with the
exact spec instead of asking again in prose. A declined approval is a stop.

## History in one calibration session

Keep the search's history in QDash, not only in the chat. A calibration session is a record of
purpose; it never replaces the scope record or any approval.

1. **One session.** Before the first run, reuse the open calibration session the user names, or
   one `qdash_list_calibration_sessions` finds for this chip and objective once the user confirms
   it; otherwise create one with `qdash_create_calibration_session` (a reviewed write) whose
   objective names the directed pair, the cooldown, and the goal. Use that one session for the
   whole search, including the final comparison; never start a second one for the same search.
2. **Baseline.** Record the incumbent with `qdash_record_calibration_decision`: `nextAction`
   `next_task`, an `experiment` with `candidateId` `incumbent`, `stage` `baseline`, `target`
   the pair (`0-1`, control first), and `evidenceTaskIds` of the incumbent's latest validated
   chain on this chip.
3. **Intent before each run.** Record the experiment before dispatching it: `nextAction`
   `adjust_and_retry` (or `repeat`), an `experiment` with the candidate index as `candidateId`,
   the stage (`screening` or `confirmation`), the target, and `requestedChanges` naming each
   CheckCrossResonance key with `value` and `previous`. Then call `qdash_run_pipeline` with
   `calibrationSessionId` and the returned `decisionId`.
4. **Reading after each run.** Record your reading citing `evidenceRunIds` (the run's
   `pipelineRunId`), the next step, and `assessment` when you judged the result. QDash reads the
   measured values from the task results; your interpretation is your statement.
5. **Declined or refused.** When the user declines a run's approval or QDash refuses it, record
   a decision that says so (`nextAction` `stop`, or the next step), so the proposed experiment
   is not left unexplained.
6. **Conclusion.** End with `nextAction` `complete` or `stop` and a `conclusion`:
   `recommend_candidate` cites the candidate's confirmation runs, `keep_baseline` cites the
   incumbent's evidence, `inconclusive` names no candidate. Closing the session records no
   conclusion; never let a status stand in for one.

`qdash_record_calibration_decision` runs without an approval card because it only appends to
the audit of a session you created; it starts nothing and changes no calibration.

## Mechanics that decide the design (qubex 1.5.0rc2)

- CheckCR fixes one drive amplitude before its iterations:
  `min(amplitude for adiabatic_safe_factor x |f_control - f_target|, max_amplitude)`, and holds it
  through every iteration. The realized value is the `cr_amplitude` output.
- `max_time_range` (ns) caps only the tomography time window of the iterations. It is not the
  gate length; changed inference can still change the resulting gate.
- The iterations stop when IX and IY are small, or when they changed little since the last
  iteration. The second is stagnation, not success; check the coefficient history figure.
- CheckCR writes `cr_duration = 0`; that is not a gate length. The ZX frequency is
  `zx_rotation_rate x cr_amplitude`.
- With its run keys unset, CreateZX90 keeps the qubex duration behavior: from `cr_duration = 0`
  it sets the CR duration to `1.05 / (8 x zx_rotation_rate x cr_amplitude) + cr_ramptime`
  (ns, GHz), rounded up to 16 ns, then fits the amplitude at that duration. When the rough fit
  finds no root it retries once with a longer duration; the task result does not flag the
  retry, so compare the published `cr_duration` with that formula. It uses the CheckCR
  `cr_ramptime` and recomputes rotary amplitude and DRAG betas from defaults.
- CreateZX90 accepts only a fitted root inside its scanned range and at or below its cap. When
  the final fit finds no root, qubex stores `cr_amplitude = 1.0`; QDash rejects that, the task
  fails, and the pair's qubex CR note entry is put back to the entry from just before the
  CreateZX90 call, which is this step's CheckCR result, not the incumbent. Later tasks in the
  step then do not run for the pair.
- A stored nonzero `cr_duration` is reused by a CreateZX90 that runs without a CheckCR before
  it, so always run the two together in one step.
- Completed tasks write the pair's calibration. `update_calibration_parameters: false` is not a
  sandbox: an accepted result still updates and saves the qubex calibration note. Every arm,
  the incumbent included, is recalibrated when rerun, not restored, and the last arm run is the
  pair's state.
- The benchmark's reference RB is built with the candidate's own ZX90, so two independent IRB
  runs are not paired measurements.

### Scan check before every dispatch

CreateZX90 inherits the CheckCR bounds: CheckCR publishes the `adiabatic_safe_factor` and
`max_amplitude` it used as `cr_adiabatic_safe_factor` and `cr_max_amplitude`, and a CreateZX90
with those run keys unset uses them. Its cap is
`C = min(max_amplitude, amplitude for adiabatic_safe_factor x |f_control - f_target|)`, the
same formula that fixes the CheckCR drive, so in one step with unchanged frequencies `C` equals
the realized CheckCR `cr_amplitude`. qubex clips every CreateZX90 sweep, retry included, to `C`,
and QDash rejects a root above `C`. B concerns the control CR amplitude; the target's cancel
and rotary amplitudes are derived from it and bounded by no exposed key.

Dispatch only when you can show from the scope record, before the run, that the CheckCR drive
stays within B: the requested `max_amplitude` is at most B, or a known factor-limited
amplitude is. CreateZX90's scan and accepted amplitude then stay within B as well. Keep
CheckCR and CreateZX90 in the same step so CreateZX90 reads this run's bounds; a CreateZX90
without a CheckCR before it reads the stored bounds, or 0.75 and 1.0 for a pair whose CheckCR
predates them. If the check fails, do not dispatch: say which bound is missing and what
evidence would establish it. A post-run check alone is not enough.

## Parameter contract

Change only these CheckCR `run` keys. Everything else stays at its stored value or task default:
frequencies, 1Q and readout parameters, ramp time, betas, rotary, `interval`, and
`readout_duration`. Leave every CreateZX90 `run` key except the stage's `shots` unset, so it
inherits this CheckCR's bounds and ramp time and keeps the qubex duration behavior.

| Key | Type | Role | Code default |
| --- | --- | --- | --- |
| `adiabatic_safe_factor` | float | Drive: scales the detuning-based amplitude limit | 0.75 |
| `max_amplitude` | float | Drive: caps the amplitude | 1.0 |
| `max_time_range` | int, ns | Tomography measurement window; not the gate length | 4096 |

In this strategy `cr_amplitude`, `cr_duration`, `zx90_gate_time`, and `zx_rotation_rate` are
measured outputs: do not set them in a call's `run` or `input`. That is a strategy boundary,
not a claim that QDash has no input overrides.

- Change one key per experiment. Change `max_time_range` only when the tomography itself is
  the diagnosed problem (a truncated window or a poor fit), never with a drive change.
- Find the binding cap first. If the realized `cr_amplitude` equals the requested
  `max_amplitude`, that cap binds; if it is lower, the factor binds. Raising the cap that does
  not bind changes nothing. If the binding cap is at its approved bound, no stronger drive is
  feasible with these keys.
- Before dispatch, skip a candidate that predictably repeats a realized condition: a raise of a
  non-binding cap, or a value whose realized amplitude would equal one already measured with
  the same measurement settings. After a run, two requests with the same realized amplitude
  and settings are one condition; a repeat counts against the repeat cap, not as a candidate.
- Report requested and realized values separately in every record.
- `shots` and `n_trials` may differ between screening and the final comparison, as the scope
  record declares, but are identical for every arm of the final comparison.
- Record each candidate's index and the fixed order or seed used. Without a random-number tool,
  use a recorded deterministic order and do not call it random.

## Search loop

1. **Plan.** Read the pair (`qdash_list_chip_couplings`), the cooldown (`qdash_list_cooldowns`),
   and the latest same-cooldown 1Q and two-qubit results of both qubits (`qdash_target_report`,
   `qdash_list_task_results`, `qdash_get_task_result`). The incumbent is the latest validated
   chain: realized `cr_amplitude`, `zx_rotation_rate`, `cr_duration`, `zx90_gate_time`, and
   `zx90_gate_fidelity` with its error. Estimate each experiment's hardware time from past
   executions (`qdash_list_executions`, `qdash_get_execution`). Stop here if 1Q is stale, the
   scope record is incomplete, or the budget cannot cover one screening run plus the reserve.
2. **Announce, then dispatch.** Before each run, post: the experiment number, the key and its
   change (from, to), the evidence that motivates it, the candidate index, the expected
   hardware time, and the budget left after it. Run the scan check, validate with
   `qdash_plan_pipeline`, record the experiment decision, then call `qdash_run_pipeline` with
   `calibrationSessionId` and `decisionId` (see the example).
3. **Wait with status.** A waiting tool blocks the chat until it returns, so wait in slices:
   `qdash_wait_execution` with `timeoutSeconds` equal to the status cadence and
   `pollIntervalSeconds` 15. It waits for the whole pipeline. A timeout means "not finished
   yet", not a failure: read `qdash_get_execution`, post a short status (running task,
   elapsed hardware time, budget left), and wait again.
4. **Read and report.** From CheckCR read the realized amplitude, `zx_rotation_rate`, the
   coefficient history (IX, IY, IZ, ZX, ZY, ZZ) and how it stopped, and the fits
   (`qdash_get_task_figures`, `qdash_analyze_figure_json`, `qdash_get_task_knowledge`). From
   CreateZX90 read `cr_duration`, `zx90_gate_time`, and the amplitude fit. QDash has already
   failed a run with no root or a root above the cap; report that failure as the result.
   Reject a candidate whose `cr_duration` exceeds the formula's, which means a retry. Post the
   measured evidence, the decision, and the incumbent's values, and say that this run's
   completed tasks may have overwritten the pair's stored calibration, so the incumbent is no
   longer known to be in place. QDash records no authoritative write, so never state the
   current stored state as known. Record the reading as a decision citing the run.
5. **Decide** one of: a nearby allowed candidate; a repeat of an uncertain condition (within
   the cap); advance a candidate whose realized gate time is shorter than the incumbent's to
   `CheckZX90`, the Bell checks, `Check2QGateCoherenceLimit`, and the benchmark; revisit 1Q or
   drift when the incumbent's own values have moved; confirm; finish. Compare unwanted terms
   and fit quality with the incumbent's same-cooldown values, not with fixed numbers.
6. **Continue** with step 2 in the same conversation. Do not end the search after an arbitrary
   number of experiments or ask whether to go on while the scope allows another run. End it
   only for a reason in [Termination](#termination).

## Stop, cancel, and resume

- **Stopping the agent.** When the user says stop, declines an approval, or stops the turn,
  dispatch nothing new. Stopping a turn ends its wait at once and changes nothing in QDash; a
  running execution keeps measuring and writing on the hardware.
- **Cancelling hardware.** You have no cancel tool. Give the execution ID and say that an
  editor can cancel it with **Cancel Execution** on its QDash Execution page; a task in an
  operation that cannot be interrupted can take time to stop. Never claim it was cancelled
  until `qdash_get_execution` shows `cancelled`, then report the pair state as unverified
  until you read which tasks completed.
- **Resuming.** Nothing runs between turns or after the runtime or CLI stops. On the next turn,
  rebuild the state from QDash, not from memory: `qdash_get_calibration_session` lists the
  experiments with their measured values, the recommendation, and the latest requested run with
  its recorded execution outcome, and
  `qdash_get_calibration_session_audit` lists every decision, request, dispatch outcome, and
  execution. Read each execution (`qdash_get_execution`, `qdash_list_executions`) and its task
  results. Wait for a
  non-terminal execution; never re-dispatch an experiment whose completion is uncertain.
  Recompute the budget used from execution times, failed and cancelled runs included.

## Termination

End the search, reporting which reason applied, when:

- the user stops it or declines an approval;
- the budget minus the reserve cannot pay for the next experiment;
- every allowed candidate is measured or skipped as a predictable repeat, within the repeat cap;
- no stronger drive is feasible within the bounds;
- the scan check cannot be shown for any remaining candidate;
- a needed capability is missing, a run is refused, or a failure needs diagnosis first;
- the runtime asks you to wrap up the turn.

Then run the final comparison if the reserve allows and a candidate qualifies.

## Final comparison and report

With the reserve, rerun the best candidate and the incumbent as whole arms (CheckCR through
the benchmark), alternating, at least twice each, with the same `shots` and `n_trials`. Do not
reuse screening benchmarks as confirmation. Prefer an order that ends on the recommended arm;
do not rerun it afterwards to "restore" it, since rerunning recalibrates. Any extra run needs
its own approval and budget.

Report per arm the mean and spread of `zx90_gate_fidelity` over the confirmation runs with each
run's error, the realized CR duration and total gate time, and the hardware time used; the total
budget used and left; and the session's latest requested run (`latest_requested_run`) with its
execution outcome and whether its requested candidate is the recommended one. QDash records no
authoritative hardware write: request order and a completed execution do not prove which run
wrote last, since a run requested earlier can finish later. Never report the current or last
written pair state as known; say it is unverified and that applying the recommendation needs a
run of it. Keep the recommendation (your conclusion) separate from this observed record. Call a
candidate better only when its confirmation runs consistently exceed the incumbent's beyond
their errors; otherwise keep the incumbent as the recommendation and report a shorter gate as
unconfirmed. Repeated, uncorrected comparisons carry no significance claim. Record the
recommendation as the session's conclusion.

## Example step

Run keys must come from `qdash_get_pipeline_catalog` for these tasks. Here the factor was the
binding cap, the user allowed 0.70 to 0.80 in steps of 0.05, B is 1.0, and the other keys stay
at defaults. CreateZX90 sets no run keys, so it inherits factor 0.8 and cap 1.0 from this
CheckCR.

```json
{
  "spec_version": 2,
  "name": "zx90_q0_q1_c03",
  "targets": {"qids": ["0", "1"]},
  "steps": [
    {
      "type": "CustomTwoQubit",
      "step_name": "zx90_screen_c03",
      "execution_mode": "manual",
      "rounds": [[["0", "1"]]],
      "tasks": [
        {"name": "CheckCrossResonance", "call_id": "cr_c03", "run": {"adiabatic_safe_factor": 0.8}},
        {"name": "CreateZX90", "call_id": "zx90_c03"}
      ]
    }
  ]
}
```

Before this run, the experiment is recorded in the search's calibration session, and the run
names the returned decision:

```json
{
  "calibrationSessionId": "cs-...",
  "interpretation": "Realized cr_amplitude 0.31 is below max_amplitude 1.0, so the factor binds; raise it one step within the approved 0.70-0.80.",
  "nextAction": "adjust_and_retry",
  "evidenceRunIds": ["cpr-... (the previous screening run)"],
  "experiment": {
    "candidateId": "c03",
    "stage": "screening",
    "target": "0-1",
    "requestedChanges": [
      {"taskName": "CheckCrossResonance", "parameter": "adiabatic_safe_factor", "value": 0.8, "previous": 0.75}
    ]
  }
}
```

Then call `qdash_run_pipeline` with the spec above, `calibrationSessionId`, and that
`decisionId`.

To advance a candidate, append `CheckZX90`, `CheckBellState`, `CheckBellStateTomography`,
`Check2QGateCoherenceLimit`, and `ZX90InterleavedRandomizedBenchmarking` (with the stage's
`shots` and `n_trials`) to the same step, keeping its CheckCR run values.

## Decision record

QDash stores the record in the calibration session's audit; the chat reports it. Each
experiment has:

- intent: the decision recorded before the run, with the candidate index, stage, target, the
  requested run values with their previous values, and the evidence that motivates it;
- executed: the run that names the decision, its exact requested spec, and the run values the
  task results show, which QDash compares with the request;
- result: the measured values QDash reads from the task results (CR duration, `zx90_gate_time`,
  fidelity with error, durations) or the failure, plus your reading as a decision citing the run;
- in the chat: CheckCR stop reason and unwanted terms, predicted CR duration, unchanged keys
  stated as stored or default, hardware time of this run, budget used and left, the repeat
  count, and the next decision.

Post the record as Forum evidence only when the user asks.

## Comparing search strategies

To compare this agent with a fixed procedure or random sampling, give every strategy the same
candidate set and bounds, the same measured hardware budget, the same pair and cooldown, and
the same final evaluation protocol, fixed before the first run. Interleave strategies in time
to spread drift. Keep each strategy's adaptive screening data apart from its final evidence,
and score only the final confirmation runs. Report the planned number of comparisons; do not
present repeated uncorrected 95% intervals as global significance.
