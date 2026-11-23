# Calibration Provenance

Provenance records which accepted parameter versions a task used and produced. Task history
keeps measurements; provenance versions values actually published to the calibration database.

## Model the Lineage Graph

| Record / relation | Meaning |
| --- | --- |
| Entity | One published parameter version for a target |
| Activity | The task, manual edit, or seed import that produced it |
| `used` | Activity → input version |
| `wasGeneratedBy` | Output version → activity |
| `wasDerivedFrom` | Output version → input version |

<Diagram name="provenance-lineage" caption="A task links its accepted outputs to the exact input versions it used." />

Use the model's ID generators for entities and activities; all writers must share their format.

## Record Published Values

The task recorder saves history first, then records provenance when enabled. It resolves current
input entities, creates versions only for successfully written output destinations, and links
them to the activity and inputs. New versions close the previous current version; a unique index
protects version numbers.

Measurement-only output creates no current provenance entity. Recording failures are logged
without turning a successful measurement into a failure, so a missing edge is not proof that
the task never ran. Manual edits and seed imports have their own recording paths.

## Query the Graph

`ProvenanceService` scopes reads to the active project. It supports parameter history, upstream
lineage, downstream impact, comparisons, and change summaries. The UI follows entity IDs, not
inferred task-name relationships. See [OpenAPI](../../reference/openapi.md) for route contracts.

## Extend Provenance Recording

Create an activity and versions only after calibration updates succeed. Add dependency edges only
when the exact input entity is known. Preserve project, chip, target, execution, and task identity
throughout the graph; never infer a version solely from its parameter name.

## Implementation Files

| File | Responsibility |
| --- | --- |
| `src/qdash/dbmodel/provenance.py` | Documents and stable IDs |
| `src/qdash/repository/provenance.py` | Version writes and traversal |
| `src/qdash/workflow/engine/task/provenance_recorder.py` | Task recording |

Run `uv run pytest tests/qdash/workflow/engine/task/test_provenance_recorder.py` for recorder
changes, and repository/API provenance tests for traversal or scope changes.
