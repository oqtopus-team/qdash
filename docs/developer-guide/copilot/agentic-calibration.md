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
| Plan | `AgentPlanRunner.run_plan` (client) | Which node runs next | `max_node_executions`, the remaining action budget, the node graph |
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

The runner checks the node budget, then runs the node with three override layers: the values
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

## Statuses

Each layer keeps its own status, and the plan reads them from the outside in.

| Object | Values | Set by |
| --- | --- | --- |
| Agent session | `active`, `waiting_for_human`, `completed`, `expired`; `cancelled` is declared but no route sets it | `active` on creation; an authorised `request_human` action sets `waiting_for_human`, `complete_session` sets `completed`; a read after `expires_at` sets `expired` |
| Action decision | `authorized`, `rejected` | The policy check at proposal time; a rejection is recorded and never executed |
| Action execution | `not_started`, `queued`, then the execution's `running`, `completed`, `failed`, `cancelled`; `failed` on a dispatch error | Dispatch, then each read syncs the linked execution's status |
| Candidate | `accepted` true or false with a reason | The bounds and quality gates on the task result |
| Candidate commit, candidate set commit | `committing`, `committed`, `failed` | Reserved before the Qubit save, settled after it |
| Evaluation run | `running`, `completed`, `interrupted`, `cancelled` | The API worker; a stale heartbeat marks `interrupted` |
| Evaluation | `pending`, `running`, `completed`, `failed`, `interrupted`, `cancelled` | One per task result in the run |
| Step transition | `pass`, `retry`, `rollback`, `human_escalation` | The step runner, from the action, execution, and candidate above |
| Plan outcome | The same four transitions, with `node_path`, `completed_nodes`, `planner_decisions`, and the candidate set commit | The plan runner |

The session's `autonomy` (`confirm_each` or `auto`) and `max_rounds_per_target` are policy,
not status: they never change after creation, and `run-plan --planner evaluation` refuses a
session without `auto`.

## What the design does not do yet

- The planner runs only from the Python client; the pi runtime has no tool that starts an
  autonomous plan.
- A plan is one qubit; parallel plans over topology groups are not implemented.
- `ConfigureEF` ordering is not preflighted: each hardware pipeline step gets a fresh
  Experiment, so it must sit in the same step as the EF tasks it serves.
- Task results carry no failure class (platform error, missing prerequisite, measurement
  failure); the preflight and the evaluation statuses are the only taxonomy.
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
- `src/qdash/api/services/calibration_pipeline_preflight.py`: pipeline preflight
- `clients/python/tests/test_agent_runner.py`, `clients/python/tests/test_evaluation_planner.py`,
  `tests/qdash/api/services/test_agent_session_service.py`
