# Database Collections

QDash persists Bunnet documents in MongoDB; this page maps each collection to the class and module
that define its fields and indexes.

## Use the Code as the Schema

`src/qdash/dbmodel/document_models.py` is the complete registration list used by API startup.
Each document's `Settings.name` defines its collection, and `Settings.indexes` defines its managed
indexes. The document class is the source of truth for fields, defaults, validation, and indexes.

Related model layers serve different contracts:

| Layer | Source | Contract |
| --- | --- | --- |
| Persisted MongoDB documents | `src/qdash/dbmodel/` | Stored fields, collection names, and indexes |
| Domain models | `src/qdash/datamodel/` | Values shared by API, repositories, and workflow code |
| HTTP schemas | `src/qdash/api/schemas/` | Request and response payloads |
| Public API | [OpenAPI](./openapi.md) | Generated HTTP operations and schemas |

## Identity and Projects

| Collection | Document | Module |
| --- | --- | --- |
| `user` | `UserDocument` | `user.py` |
| `user_avatar` | `UserAvatarDocument` | `user_avatar.py` |
| `project` | `ProjectDocument` | `project.py` |
| `project_membership` | `ProjectMembershipDocument` | `project_membership.py` |

## Calibration and Hardware

| Collection | Document | Module |
| --- | --- | --- |
| `backend` | `BackendDocument` | `backend.py` |
| `chip` | `ChipDocument` | `chip.py` |
| `qubit` | `QubitDocument` | `qubit.py` |
| `coupling` | `CouplingDocument` | `coupling.py` |
| `task` | `TaskDocument` | `task.py` |
| `chip_history` | `ChipHistoryDocument` | `chip_history.py` |
| `qubit_history` | `QubitHistoryDocument` | `qubit_history.py` |
| `coupling_history` | `CouplingHistoryDocument` | `coupling_history.py` |
| `cryostat` | `CryostatDocument` | `cryostat.py` |
| `cooldown` | `CooldownDocument` | `cooldown.py` |
| `cooldown_wiring_event` | `CooldownWiringEventDocument` | `cooldown_wiring_event.py` |

The [Calibration Data Lifecycle](../developer-guide/workflow/calibration-data-lifecycle.md) explains
how accepted parameters, task results, and history differ.

## Executions and Workflows

| Collection | Document | Module |
| --- | --- | --- |
| `execution_history` | `ExecutionHistoryDocument` | `execution_history.py` |
| `task_result_history` | `TaskResultHistoryDocument` | `task_result_history.py` |
| `project_execution_counter` | `ProjectExecutionCounterDocument` | `project_execution_counter.py` |
| `execution_counter` | `ExecutionCounterDocument` | `execution_counter.py` |
| `execution_lock` | `ExecutionLockDocument` | `execution_lock.py` |
| `calibration_note` | `CalibrationNoteDocument` | `calibration_note.py` |
| `flows` | `FlowDocument` | `flow.py` |
| `evaluation_run` | `EvaluationRunDocument` | `evaluation_run.py` |
| `evaluation` | `EvaluationDocument` | `evaluation.py` |
| `evaluation_asset` | `EvaluationAssetDocument` | `evaluation_asset.py` |

[Workflow Engine Architecture](../developer-guide/workflow/engine-architecture.md) explains the
runtime lifecycle, reservations, and terminal state handling.

## Notes, Forum, and Notifications

| Collection | Document | Module |
| --- | --- | --- |
| `tag` | `TagDocument` | `tag.py` |
| `chip_note` | `ChipNoteDocument` | `chip_note.py` |
| `metric_note` | `MetricNoteDocument` | `metric_note.py` |
| `target_note` | `TargetNoteDocument` | `target_note.py` |
| `note_event` | `NoteEventDocument` | `note_event.py` |
| `forum_category` | `ForumCategoryDocument` | `forum.py` |
| `forum_label` | `ForumLabelDocument` | `forum.py` |
| `forum_post` | `ForumPostDocument` | `forum.py` |
| `forum_counter` | `ForumCounterDocument` | `forum.py` |
| `slack_forum_thread` | `SlackForumThreadDocument` | `slack_forum_thread.py` |
| `notification` | `NotificationDocument` | `notification.py` |
| `copilot_chat_session` | `CopilotChatSessionDocument` | `copilot_chat_session.py` |
| `copilot_chat_turn` | `CopilotChatTurnDocument` (insert-once, one per user, session, and request ID) | `copilot_chat_turn.py` |
| `dashboard` | `DashboardDocument` | `dashboard.py` |
| `metric_script` | `MetricScriptDocument` | `metric_script.py` |
| `copilot_store_teardown` | None (raw collection, one lease per owner and store) | `api/services/copilot_chat_session_service.py` |
| `copilot_store_generation` | None (raw collection, the current generation per owner and store) | `api/services/copilot_chat_session_service.py` |

[Notes Architecture](../developer-guide/architecture/notes.md) explains current-state notes and
their audit events.
[Dashboards Architecture](../developer-guide/architecture/dashboards.md) explains
dashboards, metric scripts, and their revisions. A `metric_script` document also stores the
revisions each dashboard pins (`pins`, keyed by `dashboard_id`) and a `version` write counter;
`dashboard` documents have a `version` too.

## Agent and Provenance

| Collection | Document | Module |
| --- | --- | --- |
| `agent_sessions` | `AgentSessionDocument` | `agent_session.py` |
| `agent_actions` | `AgentActionDocument` | `agent_session.py` |
| `agent_candidate_commits` | `AgentCandidateCommitDocument` | `agent_session.py` |
| `agent_candidate_set_commits` | `AgentCandidateSetCommitDocument` | `agent_session.py` |
| `agent_backend_apply_locks` | `AgentBackendApplyLockDocument` | `agent_session.py` |
| `agent_interventions` | `AgentInterventionDocument` | `agent_session.py` |
| `agent_decisions` | `AgentDecisionDocument` | `agent_session.py` |
| `calibration_sessions` | `CalibrationSessionDocument` | `calibration_session.py` |
| `calibration_pipeline_runs` | `CalibrationPipelineRunDocument` | `calibration_session.py` |
| `calibration_decisions` | `CalibrationDecisionDocument` | `calibration_session.py` |
| `pipeline_launches` | `PipelineLaunchDocument` | `pipeline_launch.py` |
| `parameter_versions` | `ParameterVersionDocument` | `provenance.py` |
| `provenance_relations` | `ProvenanceRelationDocument` | `provenance.py` |
| `provenance_activities` | `ActivityDocument` | `provenance.py` |

`agent_candidate_set_commits` was called `agent_campaign_commits` before the agent plan
vocabulary replaced "campaign". The `calibration-migration` container in `compose.yaml` runs
`python -m qdash.dbmodel.migration run --execute` before the API starts, and that run moves
the records of an existing deployment into the new collection once.

An `agent_sessions` document created in a calibration session stores its
`calibration_session_id`, its `calibration_admission` (`pending`, `admitted`, or `rejected`),
and the `calibration_reservation_id` the admission rests on; older documents have none. A
`calibration_sessions` document lists the reservations of admitted agent sessions in
`admitted_reservation_ids`. A `calibration_pipeline_runs` document stores the caller's
`reported_origin` when one was reported, the normalized `spec` it validated, and the
`decision_id` of the decision it carries out when the request named one; older runs have
neither. A `calibration_decisions` document is one append-only decision of a calibration
session's audit. A `pipeline_launches` document keeps the same
report for any dispatched pipeline, keyed by `(project_id, flow_run_id)`; both are client
reported and never verified.
[Calibration Sessions](../developer-guide/copilot/calibration-sessions.md) and
[Calibration Session Audit](../developer-guide/copilot/calibration-session-audit.md) explain
these collections.

[Provenance Architecture](../developer-guide/architecture/provenance.md) explains version,
relationship, and activity records.
