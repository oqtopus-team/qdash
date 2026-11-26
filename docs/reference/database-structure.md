# Database Collections

<a id="use-the-code-as-the-schema"></a>

MongoDB document classes in `src/qdash/dbmodel/` define stored fields, defaults, and indexes.
`document_models.py` registers them; `Settings.name` gives the collection name.
For HTTP schemas, use [OpenAPI](./openapi.md).

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

### Step Execution Metadata

New step executions add optional fields to `execution_history.note`. Existing documents, IDs,
indexes and task/artifact references remain valid; no migration or backfill is required.
Single-task executions can lack this step metadata. `step_record.py` under
`src/qdash/datamodel/` defines transform results and step keys.

| Note field | Meaning |
| --- | --- |
| `step_index` | One-based position within the step sequence |
| `step_key` | Plan-scoped occurrence key: calibration `step_id`, or transform name made unique with its position |
| `step_kind` | `calibration` or `transform` |
| `step_type` | Runtime step class name |
| `step_id` | Calibration step identity used by filter references; absent on transforms |
| `transform_result` | Copied input/output candidates, filter decisions or generated schedule |
| `pipeline.records_transform_steps` | System pipeline plan records transforms; absent in old plans |

A transform Execution has no task results or measurement artifacts. Its `calib_data_path` is
retained for schema compatibility but the directory is not created. Readers must not require
that path to exist. Saved workflows can run several sequences in one Run; step keys and indices
identify occurrences within a sequence, not globally across the Run.

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
| `copilot_chat_session` | `AgentChatSessionDocument` | `agent_chat_session.py` |
| `copilot_chat_turn` | `AgentChatTurnDocument` (insert-once, one per user, session, and request ID) | `agent_chat_turn.py` |
| `agent_chat_share` | `AgentChatShareDocument` (read-only project snapshot) | `agent_chat_share.py` |
| `dashboard` | `DashboardDocument` | `dashboard.py` |
| `metric_script` | `MetricScriptDocument` | `metric_script.py` |
| `copilot_store_teardown` | None (raw collection, one lease per owner and store) | `api/services/agent_chat_session_service.py` |
| `copilot_store_generation` | None (raw collection, the current generation per owner and store) | `api/services/agent_chat_session_service.py` |

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
| `calibration_pipeline_runs` | `RunDocument` (alias `CalibrationPipelineRunDocument`) | `run.py` |
| `calibration_decisions` | `CalibrationDecisionDocument` | `calibration_session.py` |
| `pipeline_launches` | `PipelineLaunchDocument` | `pipeline_launch.py` |
| `parameter_versions` | `ParameterVersionDocument` | `provenance.py` |
| `provenance_relations` | `ProvenanceRelationDocument` | `provenance.py` |
| `provenance_activities` | `ActivityDocument` | `provenance.py` |

The `copilot_*` names remain for compatibility after the Agent rename. The raw store collections
are defined in `src/qdash/api/services/agent_chat_session_service.py`.
See [calibration data](../developer-guide/workflow/calibration-data-lifecycle.md),
[session records](../developer-guide/agent/calibration-sessions.md), and
[provenance](../developer-guide/architecture/provenance.md) for lifecycle rules.

Automatic session lifecycle fields:

| Collection | Fields | Meaning |
| --- | --- | --- |
| `calibration_sessions` | `close_origin`, `closed_by`, `closing_note` | Manual or system closure and its recorded reason |
| `calibration_sessions` | `lifecycle_checked_at` | Sweep ordering; indexed with status and origin |
| `calibration_pipeline_runs` | `flow_end_state`, `flow_end_observed_at` | Last terminal-state evidence from lifecycle checks; not live execution status |
