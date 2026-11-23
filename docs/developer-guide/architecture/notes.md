# Notes Architecture

QDash stores current notes for fast reads and appends note events for history and search.

## Why three layers

| Layer | Purpose |
| --- | --- |
| Inline global notes and scoped note documents | Read the current annotation for the selected target and scope |
| `note_event` collection | Preserve edits for target timelines, text search, and model context |
| Note timestamp and event indexes | Avoid scanning all task results for chip-wide summaries |

## Data flow

`NoteService` writes current qubit, coupling, metric, and task-result notes, then appends their
audit events through `MongoNoteEventRepository`. Current storage depends on scope:

| Note | Current storage |
| --- | --- |
| Global qubit or coupling summary | Parent document's `note` |
| Cool-down or time-range target summary | `TargetNoteDocument` |
| Scoped metric note | `MetricNoteDocument` |
| Task-result note | `TaskResultHistoryDocument.user_note` |
| Scoped chip summary | `ChipNoteDocument` |

The dashboard combines these stores for the selected scope. Per-metric notes remain readable
as legacy context; new dashboard annotations use pinned summaries or discussions.

## Schemas

`NoteModel` stores current note content and edit metadata:

```python
class NoteModel(BaseModel):
    content: str = ""
    updated_by: str = ""
    updated_at: datetime | None = None
```

An empty `NoteModel` has no timestamp. Deleting an inline note resets it to that state; consult
the event log to distinguish deletion from a note that never existed.

`NoteEventDocument` is the audit row. Its fields and indexes are defined in
`src/qdash/dbmodel/note_event.py`; the collection is listed in
[Database Collections](../../reference/database-structure.md#notes-forum-and-notifications).

## Endpoints

### Note CRUD

| Method | Path | Purpose |
| --- | --- | --- |
| PUT | `/chips/{chip_id}/qubits/{qid}/note` | Upsert qubit's general note |
| PUT | `/chips/{chip_id}/qubits/{qid}/metric-notes/{metric_key}` | Upsert per-metric note on a qubit |
| PUT | `/chips/{chip_id}/couplings/{coupling_id}/note` | Upsert coupling's general note |
| PUT | `/chips/{chip_id}/couplings/{coupling_id}/metric-notes/{metric_key}` | Upsert per-metric note on a coupling |
| PUT | `/task-results/{task_id}/note` | Upsert per-measurement note |
| DELETE | (same paths) | Clear the corresponding note |
| GET | `/task-results/{task_id}/note` | Fetch a single task-result note |

DELETE clears the current note and appends a `delete` event. Scoped documents may be removed;
an inline note resets to an empty `NoteModel`.

### Aggregation

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/chips/{chip_id}/notes-summary` | One-fetch view: qubit notes + coupling notes + task notes for the chip. Drives the dashboard. |

The summary uses a partial index on `task_result_history.user_note.updated_at` that includes
records with a date-valued timestamp.

### Knowledge feed

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/chips/{chip_id}/note-events` | Chip-scoped chronological feed |
| GET | `/note-events/by-target?scope=&target_id=` | Per-target timeline (e.g. all events on Q5) |
| GET | `/note-events/search?q=` | Full-text search across note contents |

## Source and Tests

- `src/qdash/api/services/note_service.py`: note writes, scope resolution, summaries, and events
- `src/qdash/dbmodel/target_note.py`, `metric_note.py`, and `chip_note.py`: scoped current state
- `src/qdash/dbmodel/note_event.py`: audit event fields and indexes

Run `uv run pytest tests/qdash/api/routers/test_note.py` after changing storage or scope rules.
