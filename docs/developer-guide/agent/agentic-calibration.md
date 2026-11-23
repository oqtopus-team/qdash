# Agentic Calibration

Agentic calibration runs a bounded loop: read evidence, propose a measurement, assess its result,
and commit accepted values. QDash enforces the [session contract](./agent-platform.md).

## The model-driven loop

pi CLI and the web Agent share pi-qdash's loop tools. The model chooses tasks and assessments;
the tools reconstruct state from QDash records so a new chat can continue existing work.

### Approval

Creating a session is a reviewed write. Approval fixes targets, tasks, action and round budgets,
expiry, and autonomy. The general API can also grant override bounds and quality gates; the
pi-qdash creation tool refuses those fields and relies on task completion checks. `autonomy: auto` permits the session's steps and expert
requests without a new dialog. It does not permit unrelated writes.

### Server checks

QDash checks the authenticated creator, active status, grant, state version, pending measurements,
round limits, and repeat evidence. Identical completed measurements need an explicit repeat
reference and reason. Client checks improve errors; they never replace server enforcement.

### Dependent steps

Measurements read committed calibration state, not staged candidates. Commit an accepted frequency
before running a task that depends on it. `parameter_updates` must name the permitted outputs
and supplying tasks for a commit to use session authority.

### Quality gates

Gates constrain recorded quality metrics. The engine records fit R² as `r2`; fidelity and
frequency are output parameters, not quality metrics. A missing required metric fails the gate.
Do not invent bounds that the operator did not authorize.

### Update authority

`parameter_updates` requires `auto` autonomy and a recorded pass assessment. It can separately
permit backend application with `apply_backend`. Without this grant, commits need per-call
approval. A backend apply never implies hardware `Configure`.

### Evaluation mode

The immutable `evaluation` policy determines whether the separate QCalEval evaluator participates.
Task completion, deterministic gates, and model evaluation remain distinct evidence. Failed,
incomplete, inconclusive, or disputed evidence blocks autonomous work until expert review.

### Continuing

Read `qdash_get_agent_session_context` before continuing. Explicit user continuation works in a
new process; `qdash_wait_agent_intervention` can continue an already open turn after an answer.
An expert answer does not launch a process or enlarge the approved scope.

## The fixed-plan runner

The Python client's `AgentPlanRunner` executes an approved graph. It validates graph references,
targets, tasks, candidate parameters, and visit budgets before measuring. A dynamic planner may
choose an approved node or complete after a passing gate, but cannot add work to the graph.

### The evaluation planner

`EvaluationPlanner` evaluates a node's task result and maps the recorded diagnosis and fit
reliability to a plan decision. Invalid choices, failed evaluation, exhausted budgets, and
completion after rollback escalate to a person. Finalization revalidates every candidate before
writing the accepted set.

## Human interventions

An intervention is the durable pause record. Expert guidance is evidence, not permission.
A pause, action count, or lifecycle transition uses a conditional update on the session document;
pending payloads recover corresponding records after a crash.

Operations pass the session gate before dispatch. Work admitted before a pause may finish;
new work is refused. Resume waits for in-flight work. Stopping marks the session cancelled and
blocks later work; it must not be mistaken for proof that a hardware operation has stopped.

## Experiment audit

The audit is a read-time projection of authoritative records plus append-only decisions. Only the
creator records decisions, and doing so grants no operation. Evidence references must belong to
the session. Snapshot-bound cursors prevent silently skipping records added during pagination.

Execution grouping and session graphs are read-only views, not hardware control. For objectives
that contain multiple runs, see [Calibration Sessions](./calibration-sessions.md) and their
[audit](./calibration-session-audit.md).

## Statuses

| Session status | Meaning |
| --- | --- |
| `active` | May accept work within the grant |
| `waiting_for_human` | Paused for an expert |
| `completed` | Finished |
| `cancelled` | Stopped |
| `expired` | Grant expired |

Execution, action, evaluation, and session statuses are separate; a completed measurement does
not mean the whole session succeeded.

## Implementation and tests

| Source | Responsibility |
| --- | --- |
| `packages/pi-qdash/extensions/lib/agent-loop.ts` | Model-loop context and step checks |
| `packages/pi-qdash/extensions/tools/agent-loop.ts` | Shared loop tools |
| `src/qdash/api/services/agent_session_gate.py` | Atomic execution barrier |
| `src/qdash/api/services/agent_intervention_service.py` | Expert responses and resume |
| `src/qdash/api/services/agent_session_audit.py` | Audit projection |
| `clients/python/src/qdash/client/services/agent_runner.py` | Fixed-plan runner |

Run `task ci-pi-packages`, `task ci-agent-runtime`, and the affected agent-session API tests.
[Agent Loop Validation](./agent-validation.md) exercises a real model against the fake backend.
