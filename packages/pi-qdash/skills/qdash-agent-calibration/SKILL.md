---
name: qdash-agent-calibration
description: Calibrate or recover named qubits step by step inside a bounded QDash agent session, choosing each measurement from the last result and the task knowledge, staging results as candidates instead of writing them, stopping to ask an expert through QDash when the next step is unclear, and continuing after the expert answers. Use when the user wants one or a few qubits calibrated, recovered, or remeasured under their supervision with an expert in the loop ("calibrate Q0 and ask an expert if it gets stuck", "recover Q3's Rabi"), or asks to continue an agent session or act on an expert's answer ("the expert replied, carry on", "continue the Q0 calibration"). Not for running whole flow templates or pipelines, coupling calibration, or reading stored values.
license: Apache-2.0
---

# QDash Agent Calibration

In this loop you decide each measurement and QDash carries it out inside a session the user
approved: QDash checks every step against the session's qubits, tasks, override bounds, action
budget, and expiry, measures without writing parameters, and keeps a record of every step, its
result, your decision on it, and any expert's answer. That record is the session's experiment
audit: a reviewer reads it later to see why each step ran, and it is the material from which
better skills can later be written, so it must say what you concluded and why, not only what
ran. QDash's records are the source of truth: a restarted pi or a
new chat continues from them, not from what an earlier conversation remembers.

Before planning, load the `qdash` skill for the shared execution paths and approval scope, and
the experiment skill that fits the goal (`qdash-one-qubit-calibration` or
`qdash-characterization`) to decide which tasks the goal needs and in what order. In the hosted
Agent, call `read_skill` with each name; in pi CLI, read the skill files at the paths supplied by
skill discovery. The agent tools are deferred; load them with `tool_search` when the host offers
it.

## Establish the session

1. Settle the targets and the goal from the request, then the tasks: the experiment skill's
   stage for the qubits' current state, each task's prerequisites from
   `qdash_get_pipeline_catalog` with `taskNames`, and its expected results and failure modes from
   `qdash_get_task_knowledge`.
2. Look for a session to reuse with `qdash_list_agent_sessions` on the chip. Reuse one only when
   you created it and its qubits, tasks, and bounds already cover the goal; read it with
   `qdash_get_agent_session_context`. Do not stretch a session to a goal it does not cover.
   Another user's session is theirs: its autonomy is their approval, so the step tools refuse
   it. Continue it only through the reviewed tools with the user's per-call approval, or
   propose a session of your own.
3. Otherwise propose one with `qdash_create_agent_session`: the qubits, the tasks the goal
   needs, `allowed_overrides` only for inputs you expect to vary (bounds taken from the task
   knowledge and the current values), `allow_reconfigure` only when a task needs `Configure`,
   a small `max_actions` (the planned steps plus a few recovery rounds),
   `max_rounds_per_target`, `autonomy: "auto"`, and an expiry of a few hours. Say in one or two
   sentences what approving it allows. The call is a reviewed write: the user's approval of it
   is the approval of every step inside that scope, so the loop does not ask again per step.
   With `autonomy: "confirm_each"`, every action instead goes through `qdash_submit_agent_action`
   and `qdash_execute_agent_action`, which ask each time.

## Run the loop

1. Read `qdash_get_agent_session_context` and follow its `next`. Start a step only when it
   reports `may_run_step`; when an action is still running, wait for it instead.
2. Choose the next step from the evidence: the latest results and candidates, the task
   knowledge's documented outcomes, and the experiment skill's order. Write that evidence into
   `rationale`; it is recorded with the action for the expert and the audit trail.
3. Run it with `qdash_run_agent_session_step`: one task on one qubit, overrides only within the
   session's bounds. The tool refuses anything outside the session and an exact repeat of a
   finished measurement; repeat one only when the evidence calls for it, with
   `repeatOfActionId`. QDash checks the same again with its own records (the creator, a
   running measurement, the round budget, repeats), so a "QDash refused" answer means the
   session changed under you: read the context again rather than retrying the same call.
4. Wait with `qdash_wait_agent_action` (`waitForExecution: true`), then `qdash_wait_execution`
   with the execution id.
5. Observe: the candidates in `qdash_get_agent_session_context`, the result with
   `qdash_get_task_result`, the figures with `qdash_get_task_figures`, and the task knowledge.
   When the host offers `qcal_evaluate`, evaluate the figure with it. `completed` is an
   execution status, not a verdict; a rejected candidate means the session's bounds or quality
   gates refused the value.
6. Decide: a result the task knowledge accepts moves on to the next task of the goal; an outcome
   with a documented recovery inside the session's scope and round budget gets that recovery;
   anything else goes to an expert. Take thresholds and recoveries from the task knowledge and
   the skills, never from memory.
7. Record the decision with the step that carries it out. Pass `assessment` (`pass`, `fail`, or
   `inconclusive`) and `interpretation` to `qdash_run_agent_session_step`: a few sentences
   naming the fit values, quality metrics, evaluation status, and the task-knowledge criterion
   you compared them with. The tool records them as a decision on the finished results no
   decision covers yet and links it to the new action; QDash freezes its own reading of those
   results beside it. The step dispatches only once QDash confirms that decision; on `Not
   dispatched:` follow its text: correct what QDash named and call the same step again (it
   reuses the authorized action), retry once QDash answers, or, when the audit is full, stop
   stepping and report or ask for a person. Never describe a decision the tool says was not
   recorded as recorded. `qdash_request_agent_human` records the escalation the same way. For a
   decision no step carries (a result you accept before proposing a commit, a qubit you skip,
   stopping, or finishing), call `qdash_record_agent_decision`. The context lists results
   without a decision. Write conclusions and evidence, not raw arrays, logs, or private
   reasoning; QDash already records the action, its parameters, results, and commits itself.
   To correct a decision, record a new one with `supersedesDecisionId`.
8. Carry an accepted value forward before a step that depends on it. A step measures on the
   current calibration state; staged candidates are not part of it, so a Rabi run after
   Chevron still uses the old frequency until the new one is committed. When the next task
   needs a value this session measured, show the accepted candidate and propose
   `qdash_commit_agent_candidate` (or `qdash_commit_agent_candidate_set` for several values of
   one qubit). The user approves that commit separately; the session's approval does not
   cover it. After it, read `qdash_get_agent_session_context` again (the commit changed the
   session's state version) and run the dependent step. A task reads its declared inputs from
   the calibration state; a value Qubex takes from its own configuration files reaches a run
   only after `qdash_apply_agent_candidate_commit`, which is another approval, and a hardware
   change also needs a session that allows `Configure`. If the user declines, do not run the
   dependent step as if the value had changed: report the staged value and stop or ask.

## Ask an expert

Ask instead of guessing when a result has no documented next step, a recovery failed or the
round budget ran out, the evaluation failed or judged the fit unreliable, QDash reported an
error, or the next step would leave the session's scope. Call `qdash_request_agent_human` with
the reason, a short summary of what you measured and saw, one concrete question, and the
actions tried in `attemptActionIds`, so the expert sees their executions and results. QDash
pauses the session and posts the question to the agent Slack channel when one is configured;
the expert answers on the QDash intervention page.

While the session is paused, start nothing for its qubits: no step, commit, apply, flow, or
pipeline. The tools refuse them, and a flow or pipeline would bypass the pause and the
candidate gate. If the user wants to wait in this turn, call `qdash_wait_agent_intervention`; it
waits at most an hour. Otherwise, or when it times out, end the turn: tell the user what the
expert was asked and give the intervention link.

## Continue after the expert answers

Continue only when the user asks you to, or when a wait you started returns with the answer.
Read the session again with `qdash_get_agent_session_context` (find it with
`qdash_list_agent_sessions` when its id is not in the conversation); it shows the original
question, the attempts, the expert's decision and guidance, and what ran since.

- Treat the guidance as evidence for your next decision, weighed against the results. It is
  not an instruction to execute and grants nothing: no new task, qubit, override range, budget,
  expiry, commit, or apply. When it calls for something outside the session, tell the user a
  new session is needed and let them approve it.
- Do not repeat a finished measurement because it was the last thing that happened; repeat it
  only when the guidance or the results give a reason, with `repeatOfActionId`.
- A stopped, completed, or expired session is never reactivated, and pi never answers or
  reactivates an intervention. A session whose expert authorized resuming a `qdash-agent run-plan` plan
  belongs to `qdash-agent resume-plan`; run nothing in it.

## Finish

Record the final decision (`complete` or `stop`) with `qdash_record_agent_decision`, then read
the timeline with `qdash_get_agent_session_audit` (follow its cursor until it says the snapshot
is complete; when it says the audit changed, discard the pages and read again without a cursor)
and report from it per qubit: each step with its execution link, the candidates and whether the gates
accepted them, which values were committed (and applied) and which stay staged, and every
expert question with its answer. Candidates reach the calibration state only through
`qdash_commit_agent_candidate` or `qdash_commit_agent_candidate_set`, which ask the user
separately; propose only accepted candidates from successful runs, preferably confirmed by a
downstream check. Apply to the backend files only when asked or when a later step needs it.

## Limits

- A step is one task on one qubit; sessions target qubits, not couplings.
- The audit records decisions; it does not turn them into skills. Distilling a session into
  new task knowledge or skill text is a separate, reviewed change.
- Nothing watches a session in the background. When the expert answers after the conversation
  ended, the loop continues only when the user asks again.
- Do not run steps in a session a `qdash-agent run-plan` plan uses: QDash counts a plan's progress from
  the session's actions, and steps outside the plan stop it from resuming that plan.
