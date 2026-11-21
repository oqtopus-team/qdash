# Agentic Calibration

Agentic calibration is the closed loop in which an agent decides the next measurement and QDash
performs it, judges it, and records it. The loop runs on the agent side as a **plan**: a graph of
nodes a person approved once, each node one task on one qubit with one candidate parameter.
A plan with `autonomy: auto` is an **autonomous plan**: after every node the agent evaluates
the result with the calibration-evaluation model and follows the task knowledge's
`next_actions` table instead of the plan's fixed edges. The platform contract behind the loop
(sessions, actions, gates, commits) is in [Agent Platform](./agent-platform.md); the operator's
procedure is in [Agent Calibration](../../user-guide/agent-calibration.md#run-a-plan).

<Diagram name="agentic-calibration-loop" caption="The plan, the step runner, and the evaluation planner run outside QDash. QDash authorises each action, measures without writing, gates the candidate, evaluates the figure against the task knowledge, and commits only the accepted set." />

## Three loops, one boundary

The design keeps three loops apart so that each can be bounded and audited on its own.

| Loop | Where it runs | Decides | Bounded by |
| --- | --- | --- | --- |
| Step | `AgentCalibrationRunner.run_step` (client) | Whether one measurement produced an accepted candidate | The session grant: tasks, qubits, overrides, quality gates, state version |
| Plan | `AgentPlanRunner.run_plan` (client) | Which node runs next | `max_node_executions`, `max_node_visits` per node, the remaining action budget, the node graph |
| Evaluation | `EvaluationPlanner.choose_next` (client) with `POST /evaluations/runs` (API) | Which plan node the evaluated status leads to | `next_actions`, `max_rounds_per_target`, the session's override bounds |

Every decision crosses the boundary as a request QDash can refuse. The agent never writes a
parameter, never widens its scope, and never runs a task the plan does not name; the planner
returns a node id, not a task. A model's judgement reaches the hardware only through the
`next_actions` table a person wrote into `task.md`.

## Before the first measurement

Two checks run before any hardware time is spent, so that a plan fails for a reason a person
can read rather than in the task's own validation.

The plan runner validates the graph (unique ids, known targets, no reserved `$complete`,
`$default`, or `$escalate` id) and the session policy: the qubit, every task, every candidate
parameter, reconfiguration if a node asks for it, and `max_node_executions` against the actions
the session still has. A failure is returned as `human_escalation` with no action created.

The pipeline preflight in `POST /calibration-pipelines/validate` covers the agent's other
entry point, `qdash_run_pipeline`: run-parameter names and types, the session-scoped
`readout_duration`, and the calibrated inputs each qubit task needs, including the readout
duration the stored Rabi parameters were measured with. See
[Calibration Pipeline](../workflow/calibration-pipeline.md#preflight-checks) and
[Parameter Resolution](../workflow/parameter-resolution.md).

## One node visit

<Diagram name="agentic-calibration-plan-states" caption="A node visit: budget, run, outcome, planner decision, node rule. Red boxes end the plan for a person; the evaluation planner's rules fill the decision box." />

The runner checks the node budget (`max_node_executions` for the plan, `max_node_visits` for
the node about to run, whichever rule led back to it), then runs the node with three override
layers: the values
earlier nodes accepted (carried), the node's own `parameter_overrides`, and the one-shot
overrides a planner attached to its last decision. Each visit gets a deterministic idempotency
key from the plan prefix, the node index, and the visit count, so a revisit is a new action
while a transport retry before dispatch reuses the same one.

The step outcome is one of four transitions:

| Transition | Meaning | What the plan does |
| --- | --- | --- |
| `pass` | The candidate passed the session's bounds and quality gates | Carries the value, counts a completed node, asks the planner, then follows `on_pass` or the next node |
| `rollback` | The candidate was rejected; nothing is carried | Asks the planner, then follows `on_rollback` or stops |
| `retry` | No measurement happened, or QDash timed out | Re-runs with the same key only while no operation id exists and `max_pre_dispatch_retries` allows; otherwise returns |
| `human_escalation` | The action was rejected by the policy, or a planner or graph error | Returns at once |

The planner's answer is checked before it is used: an unknown node, overrides on a sentinel,
a non-finite override, or `$complete` after a `rollback` ends the plan as `human_escalation`.
A planner that raises ends it the same way. `$default` is recorded and the node's own rule
applies.

With `commit_on_success`, a plan that ends in `pass` commits the latest accepted candidate per
parameter as one **candidate set**: QDash re-resolves each referenced task result, re-runs the
gates, and writes the set with one Qubit save and one audit record
(`POST /agent-sessions/{id}/candidate-set-commits`). Any other ending leaves every value
uncommitted.

## The evaluation planner

`EvaluationPlanner` is the only planner shipped with QDash. It turns the calibration
evaluation into a plan decision without adding any judgement of its own:

1. It creates an evaluation run for the node's task result (`trigger: single`) and waits for it.
2. It reads the status question's answer (`status`, `suggested_range`) and the fit question's
   (`fit_reliability`), as [Calibration Evaluation](./evaluation.md) defines them.
3. It looks the status up in the task's `next_actions` (`GET /tasks/{name}/knowledge`).
4. It checks any override against the session's `allowed_overrides` and the target node's
   visits against `max_rounds_per_target`.

The keys of `next_actions` are exactly the statuses the evaluation can report for that task:
`SUCCESS` plus one code per bullet under `## Common failures` in `task.md`
([Knowledge Layout](./knowledge-layout.md)). CheckRabi's table today reads:

| Status | Action | Effect in the plan |
| --- | --- | --- |
| `SUCCESS` | `continue` | `$default`: the node's `on_pass` or the next node |
| `NO_SIGNAL` | `run_task: CheckChevron` | Jump to the plan node that runs CheckChevron; its accepted `qubit_frequency` is carried on |
| `LOW_CONTRAST`, `RAPID_DECAY`, `FREQUENCY_MISMATCH`, `BEATING_PATTERN` | `request_human` | `$escalate` with the entry's note as the reason |

A `retry` entry re-runs the same node with the entry's `overrides`, or with the midpoint of the
evaluation's suggested range when `suggested_range_parameter` names the parameter. No CheckRabi
entry uses it, because the evaluator's range describes the swept pulse duration rather than
an input.

The planner stops the plan (`$escalate`) when the table has no entry for the status, when the
same status comes back three times for one node, when the fit was unreliable twice in a row,
when a node would exceed `max_rounds_per_target`, when an override leaves the session bounds,
and when the evaluation was skipped, failed, or timed out. Each decision is kept as an
`EvaluationPlannerTrace` and printed by `run-plan` under `evaluations`, so a reviewer can
record a verdict on every evaluation that steered the run.

## Human interventions

An intervention is QDash's durable record that an agent stopped and needs a person. It is the
only thing that pauses a session for a human, and QDash is its source of truth: Slack only
points to it. The operator's procedure is in
[Agent Calibration](../../user-guide/agent-calibration.md#when-the-agent-stops-for-an-expert).

There are two entry points, and only these:

| Entry point | Records | Resume |
| --- | --- | --- |
| `AgentPlanRunner.run_plan(record_interventions=True)`, the default of `qdash-agent run-plan` | Every non-pass ending, with an `AgentInterventionReason`, the step outcomes as references, and a plan checkpoint | `qdash-agent resume-plan` claims the resume and continues the plan |
| An authorised `request_human` action (`qdash_submit_agent_action` in pi or chat) | The diagnosis as the question, linked to the action, without a checkpoint | The expert's resume reactivates the session; the agent continues with its own proposals |

The pi runtime does not run plans, so there is no automatic resume for chat; a chat agent reads
the answer with `qdash_list_agent_interventions`.

The plan runner classifies each ending: the evaluation planner sets `escalation_reason` on its
`$escalate` decisions (`unknown_outcome` for a status without a `next_actions` entry,
`recovery_exhausted` for a round or repeat limit, `evaluation_failed` for a failed, skipped, or
unreliable evaluation, `policy_limit` for an override outside the bounds, `agent_request` for a
`request_human` entry), and the runner classifies its own stops (budgets and visit limits as
`recovery_exhausted`, policy rejections and preflight refusals as `policy_limit`, API and
execution failures as `platform_error`). A known recoverable status stays in the bounded loop
and records nothing.

`POST /agent-sessions/{id}/interventions` pauses an active session and records the
intervention in one compare-and-set on the session document (see
[The execution barrier](#the-execution-barrier)). The request does not carry an expected state
version; the server retries up to five times against the current version, so a concurrent
action delays the stop, and only a session that keeps changing returns 409. Recording needs neither `run_task` budget nor an unexpired session:
on an expired, completed, or cancelled session the record is kept with `pauses_session: false`
and can only be closed. The server checks that every referenced action
belongs to the session, that executions, task results, and evaluations exist in the project, and
that targets, tasks, and checkpoint nodes are inside the policy. A repeated request with the same
idempotency key returns the same record; a second intervention while the session already waits
is refused with the waiting one's id.

The checkpoint holds the approved plan, its idempotency prefix, `node_path`, per-node visit
counts, the stopped node, the accepted candidates as `(action_id, parameter_name, task_id)`, the
plan bounds, and the evaluation planner's stop-rule history. The runner writes it, so the server
reconciles it with its own records before accepting it
(`AgentInterventionService._validate_checkpoint`):

- **One plan per session.** The first checkpoint binds the session to its plan: the pause stores
  the prefix, the hash of the nodes, the target, and the bounds in the session's
  `plan_binding`. A later checkpoint that changes any of them is refused with 422, so a fresh
  prefix or a raised `max_node_visits` cannot restart the budget. An evaluation-planned
  checkpoint must limit node visits to the policy's `max_rounds_per_target`.
- **Counts from QDash's actions.** Every `run_task` action of the session must carry a plan key
  (`{prefix}-node-{index}[-visit-{n}]-action`) whose node has the action's task, target, and
  override names; a session that also ran actions outside the plan cannot record a checkpoint.
  A node's visits may be higher than its actions show, because a visit can stop before its
  action reaches QDash, but never lower. The visit counts must match `node_path`, and the path
  must extend the one the previous checkpoint recorded.
- **Candidates from the plan's runs.** Each carried candidate must name an authorised action of
  the plan, the `candidate_parameter` of that action's node, and the task result of that
  action's execution, task, target, and chip; one candidate per parameter.

A checkpoint that breaks the policy or contradicts itself (visit counts that do not match its
`node_path`, two candidates for one parameter, an evaluation planner without the visit limit)
is refused with a plain 422, like any other invalid reference. A well-formed checkpoint that
QDash's records do not support (a changed plan, a path or planner history that does not extend
the recorded one, a session that also ran `run_task` actions outside the plan, lowered visits,
or a candidate that no run of the plan produced) is refused with 422 and
`detail: {"code": "checkpoint_rejected", "message": ...}`. These reconciliation checks run after
every other check, so the code never covers a scope, reference, or format failure. Nothing of
the rejected checkpoint is stored.

On that code alone, `AgentPlanRunner` records the stop again without a checkpoint, under the
idempotency key with `-nocp` appended and with a fixed sentence appended to the summary, so the
session still pauses and Slack is still notified. The runner keeps QDash's message in
`AgentPlanOutcome.checkpoint_rejection` (`checkpoint_rejection` in the `run-plan` output) and
does not send it in the record. Such a record has no plan to resume: `claim-resume` refuses it,
`resume_state_from_intervention` raises, and an expert's resume only reactivates the session. A
401, 403, 409, transport failure, or any other 422 is reported in `intervention_error` without a
second request.

Resume blockers and the **Resume from** options count each node's visits as the larger of the
checkpoint and the actions, and a resume is blocked when the checkpoint is not the bound plan.
Because action keys derive from the prefix, the node index, and the visit count, a resumed node
is a new visit with a new key, and re-running an interrupted resume reproduces the keys of the
actions it already submitted, which QDash returns instead of measuring again. A planner that
decides differently on the re-run can still choose a node the first run did not reach. The
resumed runner re-reads each carried candidate from QDash and stops if one is no longer
accepted. The planner's stop-rule history is only checked for not shrinking; the hard bounds
are the visit counts, the node executions, and the session's action budget.

The expert's answer (`POST .../respond`) is bound to the session's state version. Resume is
refused while a blocker holds: the session is not paused on this intervention, it expired, it
used all its actions, its remaining actions do not cover the plan's remaining node executions,
the chosen node is at its visit limit, or an operation that passed the session's execution gate
has not settled: a measurement, a candidate commit, or a backend apply. A stop cancels the
session and is never blocked. A resume of a plan with a checkpoint sets
`resume_authorized` and keeps the session paused; `POST .../claim-resume` with a claim key then
reactivates it for one runner, re-checking the blockers, and `POST .../resume-outcome` records
how the resumed run ended. Guidance is stored text; it never becomes an override, a target, or a
write. `qdash-agent resume-plan` prints it with the result and does not pass it to a planner or a
model; a chat agent can read it with `qdash_list_agent_interventions`.

A resumed run is complete only when its outcome is recorded. If `POST .../resume-outcome`
fails, `resume-plan` prints the result, exits with status 3, and prints a command that records
the outcome with `--record-outcome` and the same claim key, which claims and runs nothing. Once
an outcome is recorded, `resume-plan` with that claim key prints it and exits without running;
another claim key is refused.

The answer touches two documents. The intervention is written first as `responding`, the
session's compare-and-set carries the response id in `intervention_resolution_id`, and the
intervention is then settled. A read settles a response that a crash left half applied: it
finishes it when the session carries its response id and rolls it back to `open` after 60
seconds otherwise. The claim settles the same way through `resume_claim_key`.

### The execution barrier

QDash's MongoDB is a standalone server, so no multi-document transaction is available. The
barrier that keeps a paused session from changing hardware, backend, or calibration state is
built from single-document compare-and-set updates on the session document, which MongoDB
applies one at a time. `src/qdash/api/services/agent_session_gate.py` holds it.

- **Pause.** One update moves the session from `active` to `waiting_for_human`, sets
  `active_intervention_id`, and stores the intervention record (and, for `request_human`, the
  action record) in `pending_intervention`. The records are then inserted into their
  collections, and the payload is cleared. Every load of the session, and the Slack sweeper,
  inserts a payload that a crash left behind; the inserts are idempotent, so a retry with the
  same idempotency key returns the same intervention, and no record exists without its pause.
- **Operations.** Dispatching a `run_task` action, dispatching a backend apply, and saving a
  candidate commit each mark their own record as reserved first (`dispatching` with an
  unconfirmed token, or a commit in `reserving`), then pass a session update that matches only
  `status: active`, then confirm the reservation and start. If the pause wins the session
  first, the gate refuses with 409, the reservation is released, and nothing is sent; the
  action stays authorised for a resumed session.
- **In flight.** An operation that passed the gate before the pause continues: a pause does not
  stop a measurement or apply already sent to the worker, nor a Qubit save already reserved.
  Its record shows it as in flight, and resume stays blocked until it settles. A resume reads
  these records while the session is paused, so no new operation can pass the gate between
  that read and the update that resumes the session.
- **Crashed requests.** A reservation that never passed the gate is released after 60 seconds,
  with a compare-and-set that makes a stalled request's later confirmation fail. A confirmed
  dispatch whose request crashed before the run was recorded is never released, because QDash
  cannot tell whether the run started; the expert stops the session instead.

Slack delivery is recorded on the intervention after it is saved
(`AgentInterventionService.deliver_notification`). An attempt takes a two-minute lease with a
compare-and-set, posts the root message with the shared bot to `SLACK_AGENT_CHANNEL_ID`, and
stores the channel and timestamp; a stored timestamp is never posted again. A failure is retried
with exponential backoff (30 seconds doubling, at most 30 minutes) by a sweeper each API worker
starts when the channel is configured, and is marked `failed` after six attempts;
`POST .../notification/retry` makes one more attempt. Status changes reply in the thread. The
stored `last_error` and `last_reply_error` hold only the exception type and, for a Slack API
error, Slack's error code (`SlackApiError: channel_not_found`), never the exception text, which
can quote request headers or the token; the warning log uses the same summary. A post
that times out after Slack accepted it is indistinguishable from a lost one, so delivery is at
least once, not exactly once.

## Statuses

Each layer keeps its own status, and the plan reads them from the outside in.

| Object | Values | Set by |
| --- | --- | --- |
| Agent session | `active`, `waiting_for_human`, `completed`, `cancelled`, `expired` | `active` on creation; recording an intervention (directly or with an authorised `request_human`) sets `waiting_for_human`; an expert's resume or a runner's claim sets `active` again, an expert's stop sets `cancelled`; `complete_session` sets `completed`; a read after `expires_at` sets `expired`, paused or not |
| Intervention | `open`, `responding`, `resume_authorized`, `resumed`, `stopped`, `discarded` | See [Human interventions](#human-interventions); current servers no longer set `discarded` |
| Intervention Slack delivery | `disabled`, `pending`, `sending`, `sent`, `failed` | The API's delivery attempts |
| Action decision | `authorized`, `rejected` | The policy check at proposal time; a rejection is recorded and never executed |
| Action execution | `not_started`, `dispatching`, `queued`, then the execution's `running`, `completed`, `failed`, `cancelled`; `failed` on a dispatch error | Dispatch, then each read syncs the linked execution's status; see [The execution barrier](#the-execution-barrier) |
| Candidate | `accepted` true or false with a reason | The bounds and quality gates on the task result |
| Candidate commit, candidate set commit | `reserving`, `committing`, `committed`, `failed` | `reserving` until the session gate passes, `committing` during the Qubit save, settled after it |
| Evaluation run | `running`, `completed`, `interrupted`, `cancelled` | The API worker; a stale heartbeat marks `interrupted` |
| Evaluation | `pending`, `running`, `completed`, `failed`, `interrupted`, `cancelled` | One per task result in the run |
| Step transition | `pass`, `retry`, `rollback`, `human_escalation` | The step runner, from the action, execution, and candidate above |
| Plan outcome | The same four transitions, with `node_path`, `completed_nodes`, `planner_decisions`, and the candidate set commit; a non-pass ending adds `escalation_reason`, `checkpoint`, and the recorded `intervention` | The plan runner |

The session's `autonomy` (`confirm_each` or `auto`) and `max_rounds_per_target` are policy,
not status: they never change after creation, and `run-plan --planner evaluation` refuses a
session without `auto`. With that planner, `max_rounds_per_target` is passed to the runner as
`max_node_visits`, and a plan node that commits or applies on its own is refused, because the
planner may escalate after the value is already written; only `commit_on_success` writes.

## What the design does not do yet

- The planner runs only from the Python client; the pi runtime has no tool that starts an
  autonomous plan.
- A plan is one qubit; parallel plans over topology groups are not implemented.
- `ConfigureEF` ordering is not preflighted: each hardware pipeline step gets a fresh
  Experiment, so it must sit in the same step as the EF tasks it serves.
- Task results carry no failure class (platform error, missing prerequisite, measurement
  failure); the preflight, the evaluation statuses, and the intervention reasons are the only
  taxonomy.
- Slack messages carry no buttons, and Slack replies do not reach QDash; experts answer on the
  intervention page.
- Interventions and expert answers are kept for later review; nothing turns them into skill or
  task-knowledge changes.
- Nothing compares the evaluation's verdicts with a person's; the traces exist so that such a
  comparison can be built.

## Implementation Files

- `clients/python/src/qdash/client/services/agent_runner.py`: step runner, plan runner,
  planner protocol and sentinels
- `clients/python/src/qdash/client/services/evaluation_planner.py`: evaluation planner, range
  parsing, traces
- `clients/python/src/qdash/client/services/agent_cli.py`: `start-session --autonomy`,
  `run-plan --planner evaluation`
- `src/qdash/datamodel/agent_session.py`: session policy, `AgentAutonomy`, statuses
- `src/qdash/datamodel/task_knowledge.py`: `NextAction`, `status_codes()`, `next_action_problems()`
- `src/qdash/api/services/agent_session_service.py`: action policy, candidate gates, candidate set
  commit
- `src/qdash/api/services/agent_intervention_service.py`,
  `src/qdash/api/services/agent_intervention_slack.py`: interventions, resume, Slack delivery
- `src/qdash/api/services/agent_session_gate.py`: execution barrier, pause recovery, in-flight
  checks
- `ui/src/components/features/agent-session/`: session and intervention pages
- `src/qdash/api/services/calibration_pipeline_preflight.py`: pipeline preflight
- `clients/python/tests/test_agent_runner.py`, `clients/python/tests/test_evaluation_planner.py`,
  `tests/qdash/api/services/test_agent_session_service.py`,
  `tests/qdash/api/services/test_agent_intervention_service.py`,
  `tests/qdash/api/services/test_agent_session_barrier.py`,
  `tests/qdash/api/routers/test_agent_intervention_e2e.py`
