# Notes Architecture

QDash stores current annotations for fast reads and appends note events for history and search.

## Data flow

`NoteService` updates the current note, then appends an event through `MongoNoteEventRepository`.
Global qubit/coupling notes live on their parent records; scoped notes use dedicated documents;
task-result notes stay with the result.

An empty inline note has no timestamp. Deletion resets it to that state; use the event history
to distinguish deletion from a note that never existed.

## Endpoints

Chip/target routes edit notes and read summaries. Note-event routes provide target timelines and
text search. Use the [OpenAPI reference](../../reference/openapi.md) for exact routes and schemas.
All reads and writes must preserve project and target scope.

Chip summaries use note indexes rather than scanning every task result. Keep index changes
aligned with timestamp semantics and legacy documents.

## Source and Tests

| Source | Responsibility |
| --- | --- |
| `src/qdash/api/services/note_service.py` | Scope resolution, writes, summaries, events |
| `src/qdash/dbmodel/target_note.py` | Scoped target notes |
| `src/qdash/dbmodel/metric_note.py` | Scoped metric notes |
| `src/qdash/dbmodel/chip_note.py` | Chip notes |
| `src/qdash/dbmodel/note_event.py` | Event history and indexes |

Run `uv run pytest tests/qdash/api/routers/test_note.py` after changing storage or scope.
Test create, edit, delete, history, and cross-project access together.
