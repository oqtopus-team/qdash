---
name: qdash-zx90-optimization
description: Search, within a user-approved hardware time budget and parameter bounds, for a shorter ZX90 gate with high fidelity on one directed coupling, choosing each small CheckCrossResonance condition change from the last result, reporting every experiment in the chat, and confirming the best candidate against the incumbent with ordinary QDash pipelines. Use when the user asks to shorten or optimize the ZX90 or CR gate of one pair ("make the Q0 to Q1 ZX90 shorter without losing fidelity", "tune the CR conditions of this pair adaptively"), or to design an agent-versus-fixed-procedure comparison of such searches. Not for calibrating pairs (qdash-two-qubit-calibration).
license: Apache-2.0
---

# QDash ZX90 Optimization

You run an adaptive search on one directed pair while the chat is open: each experiment
changes one `CheckCrossResonance` condition inside bounds the user approved, you read its
evidence, report it, and choose the next experiment. QDash tasks own the measurements and the
quality calculations (tomography fits, amplitude fit, benchmark fit, coherence limit); you own
the interpretation and the next decision. A shorter gate is a screening criterion; benchmarked
fidelity is the objective.

Load the `qdash` skill first for execution paths and approval scope, and use
`qdash-two-qubit-calibration` for the chain, its outputs, and diagnosis of a poor pair.

## What exists and what does not

| Available | Not available |
| --- | --- |
| `qdash_plan_pipeline` and `qdash_run_pipeline` with a `CustomTwoQubit` step in `manual` mode for the one pair | A QDash optimizer, flow, or scheduler that runs this search; anything that acts after your turn ends or the runtime stops |
| `CheckCrossResonance` run keys `adiabatic_safe_factor`, `max_amplitude`, `max_time_range` | qubex arguments QDash does not pass: CheckCR `cr_amplitude`, `ramptime`, `time_range`, `n_iterations`, `tolerance`; CreateZX90 `duration`, `amplitude_range`, `adiabatic_safe_factor`, `max_amplitude`, `rotary_multiple`, `duration_buffer` |
| `qdash_wait_execution`, `qdash_get_execution`, `qdash_list_executions`, task results, figures, task knowledge | A tool that cancels an execution; restoring an earlier pair state; saving a candidate without making it the current calibration |
| `ZX90InterleavedRandomizedBenchmarking` per arm | Paired multi-arm IRB and its paired statistics; agent calibration sessions on couplings (sessions target qubits) |

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
- CreateZX90 sets the CR duration to `1.05 / (8 x zx_rotation_rate x cr_amplitude) + cr_ramptime`
  (ns, GHz), rounded up to 16 ns, then fits the amplitude at that duration. When the rough fit
  finds no root it retries once with a longer duration; when the final fit finds no root it
  stores `cr_amplitude = 1.0`, which passes QDash's finite-value check. Treat that as a failure.
  It recomputes rotary amplitude and DRAG betas from defaults.
- A stored nonzero `cr_duration` is reused by a CreateZX90 that runs without a CheckCR before
  it, so always run the two together in one step.
- Completed tasks write the pair's calibration. `update_calibration_parameters: false` is not a
  sandbox: the qubex calibration note is still updated. Every arm, the incumbent included, is
  recalibrated when rerun, not restored, and the last arm run is the pair's state.
- The benchmark's reference RB is built with the candidate's own ZX90, so two independent IRB
  runs are not paired measurements.

### Scan check before every dispatch

CreateZX90 does not inherit the CheckCR cap: QDash calls it without `adiabatic_safe_factor` or
`max_amplitude`, so it uses qubex's own 0.75 and 1.0. Its sweeps are clipped to
`C = min(amplitude for 0.75 x |f_control - f_target|, 1.0)` and reach at most
`min(C, 2.4 x a)`, where `a` is the CheckCR amplitude (at most the requested `max_amplitude`).
Its final amplitude lies in the swept range, except for the 1.0 fallback. QDash enforces no
user bound on any of this. B concerns the control CR amplitude; the target's cancel and rotary
amplitudes are derived from it and bounded by no exposed key.

Dispatch only when you can show from the scope record, before the run, that:

1. the CheckCR drive stays within B: the requested `max_amplitude` is at most B, or a known
   factor-limited amplitude is; and
2. the whole CreateZX90 scan, retry included, stays within B: B is at least 1.0, or at least
   `2.4 x` the requested `max_amplitude`, or at least an established `C`. `C` is established
   only by a same-cooldown CheckCR at factor 0.75 whose realized amplitude stayed below its
   `max_amplitude`, with unchanged qubit frequencies and control drive calibration since.

If neither holds, do not dispatch: say which bound is missing and what evidence would establish
it. When B is below 1.0, the fallback leaves an out-of-bound stored amplitude that later tasks
would drive, so end a screening step with CreateZX90 and advance a candidate in a separate step
only after reading its stored `cr_amplitude` at or below B. A post-run check alone is not
enough.

## Parameter contract

Change only these CheckCR `run` keys. Everything else stays at its stored value or task default:
frequencies, 1Q and readout parameters, ramp time, betas, rotary, `interval`, and
`readout_duration`.

| Key | Type | Role | Code default |
| --- | --- | --- | --- |
| `adiabatic_safe_factor` | float | Drive: scales the detuning-based amplitude limit | 0.75 |
| `max_amplitude` | float | Drive: caps the amplitude | 1.0 |
| `max_time_range` | int, ns | Tomography measurement window; not the gate length | 4096 |

CreateZX90's run keys are `readout_duration`, `shots`, and `interval`; none shapes the gate.
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
   `qdash_plan_pipeline`, then call `qdash_run_pipeline` (see the example).
3. **Wait with status.** A waiting tool blocks the chat until it returns, so wait in slices:
   `qdash_wait_execution` with `timeoutSeconds` equal to the status cadence and
   `pollIntervalSeconds` 15. It waits for the whole pipeline. A timeout means "not finished
   yet", not a failure: read `qdash_get_execution`, post a short status (running task,
   elapsed hardware time, budget left), and wait again.
4. **Read and report.** From CheckCR read the realized amplitude, `zx_rotation_rate`, the
   coefficient history (IX, IY, IZ, ZX, ZY, ZZ) and how it stopped, and the fits
   (`qdash_get_task_figures`, `qdash_analyze_figure_json`, `qdash_get_task_knowledge`). From
   CreateZX90 read `cr_duration`, `zx90_gate_time`, and the amplitude fit; reject a 1.0
   fallback, a final amplitude above B, or a retried, longer duration. Post the measured
   evidence, the decision, the incumbent's values, and the pair's actual current stored state,
   which is now this run's result, not the incumbent.
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
  rebuild the state from the decision records: read each recorded execution ID
  (`qdash_get_execution`, `qdash_list_executions`) and its task results. Wait for a
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
budget used and left; and the actual last stored pair state with the execution that wrote it.
If that run failed or its evidence is incomplete, report the state as unverified. Call a
candidate better only when its confirmation runs consistently exceed the incumbent's beyond
their errors; otherwise keep the incumbent as the recommendation and report a shorter gate as
unconfirmed. Repeated, uncorrected comparisons carry no significance claim.

## Example step

Run keys must come from `qdash_get_pipeline_catalog` for these tasks. Here the factor was the
binding cap, the user allowed 0.70 to 0.80 in steps of 0.05, B is 1.0, and the other keys stay
at defaults. Because 0.8 exceeds CreateZX90's internal factor of 0.75, check its amplitude fit
closely.

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

To advance a candidate with B at least 1.0, append `CheckZX90`, `CheckBellState`,
`CheckBellStateTomography`, `Check2QGateCoherenceLimit`, and
`ZX90InterleavedRandomizedBenchmarking` (with the stage's `shots` and `n_trials`) to the same
step, keeping its CheckCR run values. With B below 1.0, run them as a separate step after the
stored-amplitude check.

## Decision record

Agent sessions do not cover couplings, so no QDash tool stores this record; keep it in the
conversation and the final report, and post it as Forum evidence only when the user asks. One
record per experiment:

- evidence read (task IDs, execution ID, cooldown) and the hypothesis;
- proposed: the action, the requested run values, candidate index, order or seed;
- executed: the run values the task results show and the realized `cr_amplitude`;
- unchanged: every other key, stated as stored or default;
- result: CheckCR stop reason and unwanted terms, predicted and realized CR duration,
  `zx90_gate_time`, fidelity with error, or the failure;
- hardware time of this run, budget used and left, the repeat count, and the next decision.

## Comparing search strategies

To compare this agent with a fixed procedure or random sampling, give every strategy the same
candidate set and bounds, the same measured hardware budget, the same pair and cooldown, and
the same final evaluation protocol, fixed before the first run. Interleave strategies in time
to spread drift. Keep each strategy's adaptive screening data apart from its final evidence,
and score only the final confirmation runs. Report the planned number of comparisons; do not
present repeated uncorrected 95% intervals as global significance.
