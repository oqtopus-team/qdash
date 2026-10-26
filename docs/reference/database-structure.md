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

Do not copy a field or index definition into documentation when the code can answer it directly.
Explain lifecycle and ownership decisions in the Developer Guide instead.

## Identity and Projects

| Collection | Document | Module |
| --- | --- | --- |
| `user` | `UserDocument` | `user.py` |
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

[Notes Architecture](../developer-guide/architecture/notes.md) explains current-state notes and
their audit events.

## Agent and Provenance

| Collection | Document | Module |
| --- | --- | --- |
| `agent_sessions` | `AgentSessionDocument` | `agent_session.py` |
| `agent_actions` | `AgentActionDocument` | `agent_session.py` |
| `agent_candidate_commits` | `AgentCandidateCommitDocument` | `agent_session.py` |
| `agent_candidate_set_commits` | `AgentCandidateSetCommitDocument` | `agent_session.py` |
| `parameter_versions` | `ParameterVersionDocument` | `provenance.py` |
| `provenance_relations` | `ProvenanceRelationDocument` | `provenance.py` |
| `provenance_activities` | `ActivityDocument` | `provenance.py` |

`agent_candidate_set_commits` was called `agent_campaign_commits` before the agent plan
vocabulary replaced "campaign". The `calibration-migration` container in `compose.yaml` runs
`python -m qdash.dbmodel.migration run --execute` before the API starts, and that run moves
the records of an existing deployment into the new collection once.

[Provenance Architecture](../developer-guide/architecture/provenance.md) explains version,
relationship, and activity records.
