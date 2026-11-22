---
name: qdash-agent-calibration
description: Calibrate or recover named qubits step by step inside a bounded QDash agent session, choosing each measurement from the last result and the task knowledge, committing passing values under the update authority the user approved with the session, stopping to ask an expert through QDash when a result is failed, uncertain, or unexplained, and continuing after the expert answers. Use when the user wants one or a few qubits calibrated, recovered, or remeasured under their supervision with an expert in the loop ("calibrate Q0 and ask an expert if it gets stuck", "recover Q3's Rabi"), or asks to continue an agent session or act on an expert's answer ("the expert replied, carry on", "continue the Q0 calibration"). Not for running whole flow templates or pipelines, coupling calibration, or reading stored values.
license: Apache-2.0
---

# QDash Agent Calibration

In this loop you decide each measurement and QDash carries it out inside a session the user
approved: QDash checks every step against the session's qubits, tasks, override bounds, action
budget, and expiry, measures without writing parameters, commits a value only through a commit
QDash checks, and keeps a record of every step, its
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
   stage for the qubits' current state, each task's prerequisites and its declared input and
   output parameters with units from `qdash_get_pipeline_catalog` with `taskNames`, and its
   expected results and failure modes from `qdash_get_task_knowledge`. Read the current values
   once (`qdash_query` `qubit_latest` needs `task`). This is enough to plan; older sessions'
   results are already in the calibration state and the task results.
2. Look for a session to reuse with `qdash_list_agent_sessions` on the chip (active and
   waiting sessions). Reuse one only when you created it and its qubits, tasks, and bounds
   already cover the goal; read it with `qdash_get_agent_session_context`. Do not stretch a
   session to a goal it does not cover. When the user asks for a new session, propose one
   without reading the older ones. Another user's session is theirs: its autonomy is their
   approval, so the step tools refuse it. Continue it only through the reviewed tools with the
   user's per-call approval, or propose a session of your own.
3. Plan which values the goal must commit. A step measures on the committed calibration state,
   so when a later task needs a value an earlier task of this goal measures (CheckRabi at the
   frequency CheckChevron just measured), that output has to be committed between them. QDash
   uses `allowed_overrides` for two things: a step may override a task input of that name
   within the bounds, and a task output of that name becomes an accepted candidate only inside
   them. An output that is not a key is staged as rejected and can never be committed from this
   session, and a session's policy cannot change after approval. So put each output the goal
   must commit in `allowed_overrides`, under the output name and in the unit the catalog lists,
   and nothing the goal does not need: a key is also scope the user grants. When the goal
   commits values, propose `parameter_updates` in the same policy: `parameters` (exactly the
   outputs the goal commits), `tasks` (only the tasks that measure them), and `apply_backend`
   only when a later step reads the value from Qubex's configuration files rather than from
   QDash. Approving the session then lets you commit those values after a result you assess as
   pass, without asking per update. Without `parameter_updates`, every commit and apply is a
   separate approval.
4. Take every bound from evidence, never from a habit or a round number: the range the task
   knowledge documents for the value, or a window around the current value that the task
   knowledge or the experiment skill justifies. When neither documents a range, do not invent
   one and do not widen a bound to be safe; a broad range turns the gate into no gate. Show the
   user the current value with its unit and ask them for the accepted window, or put a proposed
   window in the session proposal and say plainly that it is your suggestion with no documented
   basis, so that approving the session is the user's decision on it. The bound is a
   deterministic sanity check, not a scientific verdict. Each `parameter_updates` parameter
   needs both a minimum and a maximum; the task's own completion checks (such as its fit R²
   threshold) and any `quality_gates` you can justify from the task knowledge apply on top. Do
   not ask the user to invent extra thresholds: propose only the bounds the goal needs, say
   where each comes from, and let the approval decide.
5. Propose the session with `qdash_create_agent_session`: the qubits, the tasks the goal
   needs, the `allowed_overrides` from steps 3 and 4 (plus run inputs you expect to vary, such
   as `shots`), `allow_reconfigure` only when a task needs `Configure`, a small `max_actions`
   (the planned steps plus a few recovery rounds), `max_rounds_per_target`,
   `autonomy: "auto"`, `parameter_updates` from step 3 when the goal commits values, and the
   expiry the user asked for or a few hours. Say in a few sentences what approving it allows:
   each committable output with its bounds, the tasks that may supply it, whether backend apply
   is included, and that a failed, uncertain, or unexplained result stops for a person instead
   of being committed. The call is a reviewed write: the user's approval of it is the approval
   of every step and every granted update inside that scope, so the loop does not ask again.
   Never create a new session to get around a paused one; QDash refuses an `auto` session for
   qubits one of your sessions on the chip is paused for.
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
6. Decide: a result the task knowledge accepts is a pass and moves on to the next task of the
   goal; a failed, uncertain, rejected, or unexplained result, or an evaluation that failed or
   is not a reliable `SUCCESS`, goes to an expert. QDash refuses every further step of the
   session, a repeat included, until the expert answers an intervention that cites that
   action, so there is no retry on your own. Take thresholds from the task knowledge and the
   skills, never from memory. Judge a pass only from evidence you read: the
   fit values, quality metrics, figures, and evaluation. A completed execution or an accepted
   candidate alone is not a pass.
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
   Chevron still uses the old frequency until the new one is committed.
   - When the session's approval granted `parameter_updates` for the value and you judge the
     result a pass, commit it with `qdash_commit_agent_session_update`: the action, the
     parameter, and an `interpretation` citing the evidence. It records your pass assessment
     first and needs no further approval; QDash refuses it unless that pass, the bounds, the
     quality gates, the task's completion checks, and the current session and calibration
     state hold, and records the old and new value. When `apply_backend` was granted it also
     applies the value; wait with `qdash_wait_agent_candidate_apply` before the dependent step.
     Read `qdash_get_agent_session_context` again, then run the dependent step. QDash refuses
     a dependent step while the earlier value is not yet committed (or applied), and refuses
     every step, commit, and apply while any result of the session is unresolved: failed,
     assessed `fail` or `inconclusive`, rejected by the gate, missing the granted value, or
     with an evaluation that failed, has no diagnosis, or is not a reliable `SUCCESS`.
   - Never commit a failed, uncertain, rejected, or unexplained result, and never record a
     pass you do not hold to get past a refusal: call `qdash_request_agent_human` instead.
     QDash never commits a measurement any decision assessed `fail` or `inconclusive` under
     the session's authority, even after an expert answers; when the expert's answer calls
     for it, measure again within the session.
   - Without a grant for the value, show the accepted candidate and propose
     `qdash_commit_agent_candidate` (or `qdash_commit_agent_candidate_set` for several values
     of one qubit), which the user approves per call; backend files likewise go through
     `qdash_apply_agent_candidate_commit`. If the user declines, do not run the dependent step
     as if the value had changed: report the staged value and stop or ask.
   - A candidate rejected as "not allowed by the session policy" cannot be committed from this
     session: say so, and propose a new session that names that output (see Establish the
     session) instead of running the dependent step on the old value. A hardware change also
     needs a session that allows `Configure`.

## Ask an expert

Ask instead of guessing when a result has no documented next step, a recovery failed or the
round budget ran out, the evaluation failed or judged the fit unreliable, a result looks wrong
or you cannot tell, QDash reported an error or refused an update, or the next step would leave
the session's scope. Ask before committing anything from that result and before any step that
depends on it. Call `qdash_request_agent_human` with
the reason, a short summary of what you measured and saw, one concrete question, and the
actions tried in `attemptActionIds`, so the expert sees their executions and results. QDash
pauses the session and posts the question to the agent Slack channel when one is configured;
the expert answers on the QDash intervention page.

When a step fails, the wait result and the session context already hold what you need to
decide: the status, QDash's message, the effective inputs, and the absence of outputs. Call
`qdash_request_agent_human` next, citing the failed action in `attemptActionIds`, before
reading source code, older sessions, or other history. QDash refuses any further step of the
session, a repeat of the same task included, until an expert answers an intervention that
cites that action; an answer to an intervention that does not cite it clears nothing. Bring a
recovery the task knowledge documents into the question as a proposal for the expert.
The intervention is the record of the stop: it pauses the session and reaches the expert, while
a turn can end at any moment (a time limit, a provider error, the user leaving). A decision with
`nextAction: request_human`, or a question in your answer, opens nothing and reaches nobody.
After the intervention is recorded, further reading is optional and read-only; add what it
shows to your report. Say what QDash reported and do not supply a cause it did not report.

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
  expiry, commit, or apply, and it does not make a failed or uncertain result committable. When it calls for something outside the session, tell the user a
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
accepted them, which values were committed (and applied) with their old and new values and
under which authority (the session's update grant or a per-call approval), which stay staged,
and every expert question with its answer. Say that a pass is your reading and QDash's gates
are mechanical checks; neither is a scientific verdict. Commit only accepted candidates from
results you assessed as pass; apply to the backend files only when granted, asked, or when a
later step needs it.

## Limits

- A step is one task on one qubit; sessions target qubits, not couplings.
- The audit records decisions; it does not turn them into skills. Distilling a session into
  new task knowledge or skill text is a separate, reviewed change.
- Nothing watches a session in the background. When the expert answers after the conversation
  ended, the loop continues only when the user asks again.
- Do not run steps in a session a `qdash-agent run-plan` plan uses: QDash counts a plan's progress from
  the session's actions, and steps outside the plan stop it from resuming that plan.
