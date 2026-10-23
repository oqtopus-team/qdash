# Calibration Provenance

Calibration provenance records which task produced an accepted parameter value and which current
parameter versions that task used. It complements task-result history: history keeps every
measurement, while provenance versions the values published to the calibration database.

## Model the Lineage Graph

QDash uses three W3C PROV-DM concepts:

| Concept | QDash record | Meaning |
| --- | --- | --- |
| Entity | `ParameterVersionDocument` | One published value of a parameter for a target |
| Activity | `ActivityDocument` | The task, manual edit, or seed import that produced a value |
| Relation | `ProvenanceRelationDocument` | A directed edge between an entity and an activity, or between two entities |

The graph stores three relation types:

| Relation | Stored direction | Meaning |
| --- | --- | --- |
| `used` | Activity → input entity | The activity read that parameter version |
| `wasGeneratedBy` | Output entity → activity | The activity produced that parameter version |
| `wasDerivedFrom` | Output entity → input entity | The output depends on that input version |

<Diagram name="provenance-lineage" caption="One CheckT1 run records used, wasGeneratedBy, and wasDerivedFrom relations. Inputs resolve to their current version, which can come from an earlier execution." />

An entity ID has the form
`{parameter_name}:{qid}:{execution_id}:{task_id}`. An activity ID has the form
`{execution_id}:{task_id}`. Generate these IDs through `ParameterVersionDocument.generate_entity_id`
and `ActivityDocument.generate_activity_id`; graph traversal depends on every writer using the same
format.

## Record Published Values

`TaskHistoryRecorder` saves the task result first, then calls `ProvenanceRecorder` when provenance
recording is enabled. The recorder performs these operations:

1. Create the activity for the task.
2. Resolve each input's parameter name and target role, then link the activity to the current input
   entity with `used`.
3. Create a new entity for each output destination actually written to the calibration database.
4. Link each output entity to the activity with `wasGeneratedBy` and to every resolved input entity
   with `wasDerivedFrom`.

An output with `database_updates` metadata creates versions only for destinations whose `updated`
flag is `true`. Measurement-only results therefore remain in task history without becoming current
provenance entities. Older results without destination metadata use their output parameter name.

Creating an entity closes the previous current version by setting `valid_until`, then assigns the
next version number for the same project, parameter, and target. The unique version index prevents
two values from receiving the same version number.

Provenance recording is non-blocking for workflow tasks. `ProvenanceRecorder.record_from_task`
logs a recording failure instead of changing an otherwise completed calibration result. A missing
provenance edge must therefore be investigated separately from task execution.

Manual calibration edits and seed imports write through `ManualUpdateService` and
`SeedImportService`. They create their own activities and parameter versions because neither path
runs through the workflow task recorder.

<Diagram name="provenance-architecture" caption="Workflow tasks, manual edits, and seed imports write the provenance graph. ProvenanceService reads it for the Data Provenance interface and API." />

The three MongoDB collection names and their document classes are listed in
[Database Collections](../../reference/database-structure.md#agent-and-provenance). Do not repeat
their fields or indexes here; the models in `src/qdash/dbmodel/provenance.py` are the source of
truth.

## Query the Graph

`ProvenanceService` scopes every query to the active project. The API supports these query groups:

| Need | Operations |
| --- | --- |
| Inspect one value | Get an entity or the version history for a parameter and target |
| Traverse dependencies | Walk lineage toward inputs or impact toward downstream values |
| Compare and monitor | Compare executions, list recent changes, and detect degradation trends |
| Choose follow-up work | Get recalibration recommendations for an entity's downstream impact |
| Populate selectors and totals | List recent executions and get provenance statistics |

Use the generated [OpenAPI reference](../../reference/openapi.md) for routes, parameters, limits,
and response schemas. Keeping that contract generated prevents this explanation from drifting when
an endpoint changes.

The **Data Provenance** page exposes parameter history, lineage exploration, execution comparison,
and recalibration recommendations. The UI follows entity IDs through the graph; it does not infer
lineage from task names.

## Extend Provenance Recording

Use the existing repository methods when adding another writer:

1. Create one `ActivityDocument` for the operation.
2. Create parameter versions only after the corresponding calibration values are accepted.
3. Add `wasGeneratedBy` from each new entity to the activity.
4. Add `used` and `wasDerivedFrom` only when the exact input entity is known.
5. Keep `project_id`, `chip_id`, target ID, execution ID, and task ID consistent across records.

Do not create a parameter version for an unvalidated measurement or a failed database update. Do
not point an input relation at a value selected only by parameter name; resolve the exact current
entity first.

Test recorder changes in
`tests/qdash/workflow/engine/task/test_provenance_recorder.py`, repository traversal in
`tests/qdash/repository/test_provenance_repository.py`, service behavior in
`tests/qdash/api/services/test_provenance_service.py`, and HTTP contracts in
`tests/qdash/api/routers/test_provenance.py`.

## Implementation Files

| Responsibility | Source |
| --- | --- |
| Documents and stable ID generation | `src/qdash/dbmodel/provenance.py` |
| Persistence and graph traversal | `src/qdash/repository/provenance.py` |
| Workflow task recording | `src/qdash/workflow/engine/task/provenance_recorder.py` |
| API queries and analytics | `src/qdash/api/services/provenance_service.py` |
| HTTP operations and schemas | `src/qdash/api/routers/provenance.py`, `src/qdash/api/schemas/provenance.py` |
| User interface | `ui/src/components/features/provenance/` |
