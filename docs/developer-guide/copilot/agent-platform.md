# Agent Platform

QDash is the execution and safety boundary for AI agents that run calibration: the agent
proposes, QDash measures, judges, records, and writes. The user-facing procedure is in
[Agent Calibration](../../user-guide/agent-calibration.md).

## Responsibility boundary

The agent, run by its user outside QDash, owns model selection, private knowledge, diagnosis,
and the next-action proposal. QDash owns authentication, project scope, hardware execution,
scheduling, deterministic validation, parameter persistence, provenance, and audit records.
Agent instructions are versioned as skills in [pi-qdash](https://github.com/oqtopus-team/pi-qdash),
next to the tools they name (see [Knowledge Layout](./knowledge-layout.md)); a session stores a
skill's name, version, and hash rather than treating the repository-local helper as the
distribution source.

## Session contract

An agent creates a bounded session before proposing anything. The session fixes the chip, the
targets, the allowed tasks, the parameter bounds, the result-quality gates, the action budget,
the expiry, the skill identity, the model identity, and whether hardware reconfiguration is
permitted. QDash rejects an action outside that grant, an action based on a stale state version,
and a duplicate request whose idempotency key carries different arguments. The budget counts
proposed actions; committing an accepted candidate advances the state version without spending
one.

## Operation dispatch

An authorised single-task action runs through the system Prefect deployment that the workers
register at startup. The action stores the Prefect flow-run UUID as `operation_id` and resolves
the QDash execution identifier, allocated independently, through `execution.note.flow_run_id`,
so the `YYYYMMDD-NNN` execution contract of single-task re-execution is preserved and the agent
has both identifiers to poll and to cite. Agent executions are named `agent:<task>` and tagged
`agent-session:<session_id>`; manual re-execution keeps `re-execute:<task>` and the workbench
`quick-run:<task>`. The measurement runs with `update_params=false`: only the gated commit
writes.

## Candidate commit

Task output parameters stay staged until the session's parameter bounds and quality gates accept
them. The candidate is derived from the authoritative task result; R² is normalised to `r2` and
persisted as task-result provenance, and a missing required metric rejects the candidate. A
campaign ending in `pass` may revalidate the latest accepted candidate per parameter and persist
the same-qid set with one Qubit save and one audit record. There is no multi-document MongoDB
transaction behind that save.

Applying a commit to the backend is a separate worker operation, the `system-candidate-apply`
deployment: the worker re-reads the audited commit, pulls the latest configuration, updates the
mapped Qubex YAML files atomically, reads them back, pushes only the target files, and records
the base and resulting Git versions. Hardware `Configure` is never implied by a commit; it runs
only when the session grants it and a later task asks for it.

## Skill runner

The runner executes a declarative decision graph of pass and rollback branches with a
node-execution bound authorised before the first dispatch. A planner supplied by the user may
choose dynamically, but only among the pre-authorised nodes or `$complete` after a passing gate.
Retry and human escalation are terminal once a hardware operation exists: the runner retries by
itself only failures that occur before QDash returns an operation id, reusing the same idempotency
key, and a timeout after that point is returned to the operator. Revisited nodes get a new
deterministic idempotency key; transport retries before dispatch reuse the same one.

The client package carries the runners and the `qdash-agent` command
([Python client](../../reference/clients/python.md#agent-calibration)).

## Safety invariants

- The agent cannot widen its target or task scope within a session.
- Parameter overrides are validated against platform-side bounds. Hardware reconfiguration is
  off unless the immutable session policy grants it.
- Every action is idempotent and bound to an expected state version.
- An agent disconnect leaves the session resumable and not running.
- A parameter write-back needs the deterministic bounds and quality gates; a model's proposal
  alone cannot commit a value.
- Each action records its skill hash, model identity, evidence references, decision, and the
  resulting operation.
- Decision-graph references are validated before dispatch, every node visit is audited, and the
  maximum visits must fit within the session's remaining budget.
- A dynamic planner cannot grow the graph or the budget. Invalid choices, planner failures, and
  completion after a rollback escalate to a human.
- Campaign finalisation re-resolves every referenced task result and validates the whole set
  before writing calibration data.

## Relation to Vibe Calibration

[Vibe Calibration](https://arxiv.org/abs/2606.22376) is the comparison point, not evidence that
QDash has reached the same autonomy: the paper reports reusable decision-tree skills,
quantitative acceptance gates, rollback and self-healing, audited write-back, topology-defined
parallel groups, and transfer to unseen devices. QDash implements the single-qubit closed loop,
backend commit, and bounded skill campaigns described above; parallel campaigns and a
comparative evaluation against expert calibration are not implemented, and any performance
claim needs results measured on QDash's own hardware, tasks, and gates.

## References

- `src/qdash/api/routers/agent_session.py`, `src/qdash/api/services/agent_session_service.py`,
  `src/qdash/api/schemas/agent_session.py`: session contract, actions, state versions, audit
- `src/qdash/datamodel/agent_session.py`, `src/qdash/dbmodel/agent_session.py`: stored session
- `src/qdash/workflow/register_system_flows.py`,
  `src/qdash/workflow/service/agent_candidate_apply_flow.py`: system deployments, backend apply
- `clients/python/src/qdash/client/services/agent_runner.py`,
  `clients/python/src/qdash/client/services/agent_cli.py`: step and campaign runners, command
- `tests/qdash/api/services/test_agent_session_service.py`
