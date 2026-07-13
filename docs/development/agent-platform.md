# Agent Platform Architecture

QDash provides the execution and safety boundary for local AI agents that operate quantum calibration workflows.

## Responsibility boundary

The local agent owns model selection, private knowledge, diagnosis, and the next-action proposal. QDash owns authentication, project scope, hardware execution, scheduling, deterministic validation, parameter persistence, provenance, and audit records. Installable agent instructions are versioned in [oqtopus-team/skills](https://github.com/oqtopus-team/skills); QDash stores their name, version, and hash in each session rather than treating its repository-local development helper as the distribution source.

An agent must create a bounded session before proposing an action. A session fixes the chip, targets, allowed tasks, parameter bounds, action budget, expiration, Skill identity, and model identity. QDash rejects actions outside that grant, actions based on a stale session state version, and duplicate requests with conflicting idempotency keys. The action budget counts proposed agent actions; committing an accepted candidate advances the state version but does not consume another action.

## Implementation phases

1. Session contract: policy, typed actions, state versioning, idempotency, and audit records.
2. Operation dispatch: execute an authorized single-task action through the existing system Prefect deployment. The action stores the Prefect flow-run UUID as `operation_id` and resolves the independently allocated QDash execution identifier through `execution.note.flow_run_id`. This preserves the existing `YYYYMMDD-NNN` execution contract used by single-task re-execution while giving agents both identifiers for polling and provenance. Agent executions use the display name `agent:<task>`; manual single-task runs retain `re-execute:<task>`.
3. Candidate commit: keep task output parameters staged until deterministic parameter bounds and session-owned task-result quality gates accept them. A successful campaign can revalidate the latest candidate for each parameter and persist the same-qid set with one Qubit save and one audit record. Backend application is a separate worker operation with file/version verification.
4. Skill runner: execute declarative pass and rollback branches with a pre-authorized node-execution bound. A user-operated planner may dynamically choose only among those pre-authorized nodes or complete after a passing gate; retry and human escalation remain terminal after a hardware operation exists.
5. Agent SDK: provide observation and operation-watching helpers for local agents.
6. Evaluation: replay historical results, inject failures, compare multiple models, and validate a hardware canary.

## Deployment gate

Agent calibration is opt-in through `ENABLE_AGENT_CALIBRATION=true`. The API always publishes the Agent endpoints in OpenAPI so released clients have a stable contract, but returns HTTP 503 for every Agent request while the flag is disabled. Worker startup always registers the existing `system-single-task` deployment and registers `system-candidate-apply` only when the same flag is enabled. This permits a QDash release with the feature dormant, followed by a controlled canary without changing legacy single-task execution.

## Safety invariants

- The agent cannot expand its target or task scope during a session.
- Parameter overrides are validated against platform-side bounds. Hardware reconfiguration is disabled unless the immutable session policy explicitly grants it.
- Every action is idempotent and tied to an expected state version.
- Agent disconnects leave the session in a resumable, non-running state.
- Parameter write-back requires deterministic parameter and result-quality gates; an LLM proposal alone cannot commit a value. R² is persisted as normalized task-result provenance, and missing required metrics reject the candidate.
- Each action records its Skill hash, model identity, evidence references, decision, and resulting operation.
- Decision-graph references are validated before dispatch, every node visit is audited, and the maximum visits must fit within the session's remaining action budget.
- Dynamic planner choices cannot expand the graph or action budget. Invalid choices, planner failures, and attempts to complete after rollback require human escalation.
- Campaign finalization re-resolves every referenced task result and validates the complete set before writing calibration data. It does not provide a multi-document MongoDB transaction or campaign-wide backend file application.

## Evaluation questions

- Does the protocol preserve calibration yield and runtime compared with the existing workflow?
- Does server-side policy prevent unsafe execution across model and prompt variations?
- Can another agent resume a session after a crash or stale observation?
- Can the complete decision and parameter lineage be replayed from QDash records?

## Vibe Calibration comparison target

QDash uses [Vibe Calibration](https://arxiv.org/abs/2606.22376) as a comparison point, not as evidence that the current implementation has reached the same autonomy level. The paper reports reusable decision-tree Skills, quantitative acceptance gates, rollback and self-healing, audited parameter write-back, topology-defined parallel groups, and transfer to unseen devices.

The QDash validation ladder is:

1. Single-qid closed loop: staged task execution, authoritative candidate extraction, deterministic parameter/R² quality gates, audited commit, retry, rollback, and human escalation.
2. Backend commit: implemented as `system-candidate-apply`; the worker re-reads the audited commit, pulls the latest config, atomically updates mapped Qubex files, read-back verifies them, and records base/result Git provenance. Hardware `Configure` remains an explicit session grant and is exercised by the next task.
3. Skill campaign: execute a declarative characterization tree with bounded retries and explicit rollback targets.
4. Parallel campaign: use hardware-safe topology groups while preserving per-qid gates and audit records.
5. Comparative evaluation: replay historical results, run repeated power-cycle trials, and compare an agent campaign with an expert campaign on the same subset.

The minimum comparison report records completion rate, wall-clock time and time per qubit, expert-agent parameter agreement within measurement uncertainty, gate rejection and recovery counts, human interventions, coefficient of variation across repeated runs, parameter drift, token/tool-call cost, and complete session/action/execution/task/commit lineage.

The paper's reported values provide external context: 108 of 112 qubits completed in 4.7 hours, 14 of 16 agreement in a controlled subset, and repeated 8-qubit runs with a mean parameter coefficient of variation of 1.8%. QDash must produce its own results under its hardware, tasks, and gate definitions before making a performance claim.
