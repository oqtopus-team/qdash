# Agent Platform

QDash owns calibration execution, authorization, validation, and audit. The agent proposes the
next action; it cannot bypass these checks. See [Agent Calibration](../../user-guide/agent-calibration.md)
for the operator's workflow. The rationale is in [Calibration Design](./calibration-design.md).

## Responsibility boundary

<Diagram name="agent-platform" caption="An agent proposes a measurement; QDash checks its grant, stages the result, and commits only an accepted candidate." />

The agent owns diagnosis, model choice, and planning. QDash owns project access, hardware
scheduling, parameter persistence, and authoritative results. Skills are distributed with
pi-qdash; sessions record the skill's identity and hash.

## Session contract

A session fixes its chip, targets, tasks, override bounds, quality gates, action budget, expiry,
and reconfiguration permission. Actions use an expected state version and an idempotency key.
Reusing a key with different arguments is rejected.

An expert request remains possible after the action budget is spent. Commits and expert
requests advance the state version without spending another action.

`confirm_each` requires confirmation per measurement. `auto` grants bounded session work once;
it does not grant parameter updates unless `parameter_updates` explicitly permits them.
A human intervention pauses work without widening the policy. See
[Agentic Calibration](./agentic-calibration.md).

## Operation dispatch

Authorized measurements use a registered system Prefect deployment and run with
`update_params=false`. The action records the Prefect operation ID separately from the QDash
execution ID. A disconnect does not grant further actions or cancel dispatched work.

## Candidate commit

Candidates come from authoritative task results. Commits require the applicable parameter bounds,
task checks, and quality gates. A session-granted commit also requires a recorded pass assessment.
Missing required quality evidence rejects the candidate.

A backend apply is a separate worker operation against the audited commit. It updates mapped
configuration files and records Git versions. Committing a value does not implicitly configure
hardware. Reconfiguration needs its own session grant and task request.

## Safety invariants

- Measurements stay inside the immutable grant and action budget.
- A pause prevents new measurements, commits, and applies; already dispatched work may finish.
- Resume preserves policy, expiry, budget, and visit counts. Ended sessions cannot resume.
- Failed or inconclusive evidence blocks autonomous work until an expert answers an intervention.
- Single-document conditional updates enforce the gate; there is no multi-document transaction.

## Skill runner

The Python runner executes an approved graph with bounded node visits. Dynamic planners can only
choose approved nodes. Transport retries before dispatch reuse the idempotency key; once an
operation exists, uncertain outcomes return to the operator rather than silently repeating work.

## Implementation and tests

Start with `src/qdash/api/services/agent_session_service.py` and
`src/qdash/api/services/agent_session_gate.py`. Backend applies live in
`src/qdash/workflow/service/agent_candidate_apply_flow.py`; Python runners live in
`clients/python/src/qdash/client/services/agent_runner.py`.

Run `uv run pytest tests/qdash/api/services/test_agent_session_service.py` after changing the
session contract, and the runner tests when changing client execution.
