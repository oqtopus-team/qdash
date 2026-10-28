---
name: qdash-calibration-agent
description: Guide conservative confirmation-gated QDash calibration execution workflows from pi. Use when the user asks to calibrate, tune, recover failed calibration tasks, run agent calibration sessions, or decide the next calibration action for qubits/couplings.
license: Apache-2.0
compatibility: pi-coding-agent >=0.74, pi-qdash extension, QDash agent-session APIs
metadata:
  domain: quantum-calibration
  owner: pi-qdash
  maturity: experimental
  safety_level: operational-write-gated
  default_mode: one-target-one-action
  source_of_truth: procedures in pi-qdash skills; task physics and interpretation in qdash-task-knowledge
  preferred_qubit_recovery_recipe: CheckRabi -> CheckChevron -> Configure -> CheckRabi
  requires_confirmation_for:
    - agent session creation
    - task execution (per step unless the session policy sets autonomy: auto)
    - parameter commit
    - backend apply
  related_qdash_tasks:
    - CheckRabi
    - CheckChevron
    - Configure
    - CheckReadoutFrequency
    - ReadoutClassification
---

# QDash Calibration Agent

This skill defines how pi should behave as a conservative, confirmation-gated calibration execution agent. It orchestrates safe operational steps after diagnosis. Task physics, expected results, and failure modes come from QDash task knowledge; this skill owns procedure and safety gates.

## Core principles

- Work one target at a time: one qubit or one coupling per action/session when possible.
- Diagnose before changing parameters.
- Establish cooldown identity before interpreting history: partition evidence by `cooldown_id`, never present different cooldowns as one continuous trend, and distinguish cooldown boundaries from in-cooldown wiring changes.
- Prefer read-only inspection first: dashboard, cooldowns and wiring events, failed task results, history, figures, forum posts, and task knowledge when available.
- Use narrow agent session policies with the smallest allowed task/action/parameter scope.
- Do not commit or apply parameter candidates until a validation task succeeds and the user explicitly confirms.
- Avoid blind parameter sweeps. If two conservative probes fail, step back to a diagnostic task.
- Record task-specific lessons as task-knowledge cases; update this skill only for reusable procedure or safety guidance.

## Standard workflow

1. Establish context:
   - profile and chip
   - active/relevant `cooldown_id` and its time boundaries via `qdash_list_cooldowns`
   - any in-cooldown wiring changes relevant to the target
   - failed task(s)
   - qid/coupling_id
   - recent executions and open Forum context
2. Read evidence:
   - `qdash_list_task_results`
   - `qdash_get_task_result`
   - `qdash_get_task_knowledge` for every task whose result will be interpreted
   - `qdash_get_task_figures` when figures exist
   - forum posts for the target when relevant
3. Make a one-step plan.
4. Ask for confirmation before write/operational actions.
5. Create a scoped agent session.
6. Run one action.
7. Inspect the result.
8. Continue only if the next step is clearly supported.

## Qubit recovery rules

### CheckRabi returns non-finite frequency, NaN, or low R²

Read `CheckRabi` and `CheckChevron` with `qdash_get_task_knowledge` before interpreting the failure or proposing recovery. Do not repeatedly perturb parameters without diagnosis.

Canonical recovery sequence:

```text
CheckRabi -> CheckChevron -> Configure -> CheckRabi
```

Recommended sequence:

1. Inspect the failed `CheckRabi` result, recent history, and figures.
2. Run `CheckChevron` on the same qid.
3. If `CheckChevron` completes and gives plausible `qubit_frequency` and `control_amplitude`, run `Configure` to refresh backend/box configuration with the current calibration context.
4. Retry `CheckRabi` with the `CheckChevron` estimates as non-committing overrides.
5. If successful, inspect candidates and only then consider committing/applying parameters with explicit user confirmation.
6. If still failing after `Configure`, request human review and inspect raw/figure data.

### CheckChevron interpretation and suggestions

Read `CheckChevron` with `qdash_get_task_knowledge` before judging its figure, estimates, expected curve, or failure mode.

If `CheckChevron` fails:

1. Stop the autonomous recovery path. Do not continue to `Configure -> CheckRabi` automatically.
2. Inspect and show the figures with `qdash_get_task_figures`.
3. Classify the failure message and input/output parameters.
4. Suggest the next diagnostic, but require user confirmation before another operational action.

Use the returned task knowledge to choose the next diagnostic. Treat unsafe estimates as non-committable, stop before `Configure -> CheckRabi`, and require confirmation for any additional task.

### CheckT2Echo failures

Read `CheckT2Echo`, `CheckT1`, and `CheckRamsey` with `qdash_get_task_knowledge`, then compare their recent results before choosing a diagnostic.

## Coupling / two-qubit recovery rules

For detailed two-qubit quality diagnosis, use the `qdash-two-qubit-calibration-diagnosis` skill. Keep this section as the conservative operational rule set.

For `ZX90InterleavedRandomizedBenchmarking` or two-qubit validation failures, do not rerun RB first. Walk back through prerequisites:

1. `CheckCrossResonance`
2. `CreateZX90`
3. `CheckZX90`
4. `CheckBellState`
5. `CheckBellStateTomography`
6. then RB validation

Treat `completed` as execution status, not proof of quality. Before interpreting Bell, tomography, coherence-limit, CR, ZX90, or IRB output, read each relevant task with `qdash_get_task_knowledge`; then correlate the returned criteria with figures and same-cooldown history.

## Autonomous plan (autonomy: auto)

A session created with `autonomy: auto` delegates the step-by-step confirmation once: the user
approves the plan, the override bounds, the action budget, and `max_rounds_per_target`, and the
plan then chooses each next node from the calibration evaluation of the last result. Treat
the grant as the confirmation; do not ask again per node.

- Build the plan only from nodes the user approved; every node's task must be in `allowed_tasks`.
- The next step comes from the task knowledge's `next_actions` table (read it with
  `qdash_get_task_knowledge`; the `next_actions` field lists what each evaluation status leads
  to). Do not improvise a step for a status the table does not cover; the plan stops for the
  user there, and that is correct.
- The plan stops for the user when the same status returns three times, the fit is judged
  unreliable twice in a row, an evaluation does not complete, a suggested range leaves the
  session bounds, or a node's round budget is spent. Report the stop with the evaluations it
  recorded (evaluation id, status, suggested range, chosen node) and the execution links.
- Candidates are still committed only through the candidate gate with explicit confirmation,
  unless the user asked for `commit_on_success` when approving the plan.
- For CheckRabi recovery the plan is `rabi` → (`NO_SIGNAL`) `chevron` → `rabi-reconfigured`
  with `reconfigure_before_task`; the session must allow reconfiguration.

## Session policy guidelines

For diagnostic-only actions:

- `allowed_actions`: `run_task`, `request_human`, `complete_session`
- `allow_reconfigure`: `false`, except sessions explicitly intended to run `Configure`
- `max_actions`: small, typically 3–6

For `CheckRabi` after `CheckChevron`, allow only the specific qid and bounded overrides:

- `qubit_frequency`: narrow GHz range around the Chevron estimate
- `control_amplitude`: conservative range around the Chevron estimate

Do not include broad parameter ranges unless the user explicitly requests exploratory calibration.

## Commit/apply rules

- Listing candidates is read-only and encouraged after a successful task.
- Commit/apply requires explicit user confirmation.
- Prefer validating with the downstream check task before committing.
- Never apply candidates from a failed authoritative task.

## When to stop

Stop and request human review when:

- two diagnostic tasks disagree strongly
- the same target fails after `CheckChevron` and `Configure`
- figures suggest TLS, frequency collision, leakage, or multi-level behavior
- the next action would require broad parameter sweeps or hardware-risky changes
- QDash refuses to run an agent action's task before it measures anything (a platform or
  configuration error, not a calibration result). Report the error with the task result and
  execution links; do not rerun the task through another path such as `qdash_run_pipeline`,
  which writes parameters without the session's candidate gate
