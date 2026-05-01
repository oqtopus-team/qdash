# Notes Architecture

QDash's note system is designed in three layers so that day-to-day reads stay
fast while every annotation is also captured for knowledge mining.

```
┌─────────────────────────────────────────────────────┐
│ Layer 1 — Inline notes (read-optimized)             │
│   QubitDocument.note / metric_notes                 │
│   CouplingDocument.note / metric_notes              │
│   TaskResultHistoryDocument.user_note               │
│   → Fetched together with the parent doc            │
├─────────────────────────────────────────────────────┤
│ Layer 2 — NoteEvent (write-through audit log)       │
│   note_event collection                             │
│   scope / target_id / metric_key / action / actor   │
│   content / extra / created_at                      │
│   → History, timeline, text search, LLM context     │
├─────────────────────────────────────────────────────┤
│ Layer 3 — Indexes                                   │
│   task_result_history: partial sparse on            │
│     user_note.updated_at != null                    │
│   note_event: text(content) + chrono compound idx   │
└─────────────────────────────────────────────────────┘
```

## Why three layers

1. **Inline** is the source of truth for the current state. The dashboard reads
   notes alongside qubits / couplings / task results — no join, no extra
   request.
2. **NoteEvent** turns "current state" into an append-only history. It enables
   uses that inline alone cannot serve:
   - Per-target timeline ("everything ever written about Q5")
   - Cross-chip text search ("which qubits have been called 'unstable'?")
   - LLM context feeds without scanning every parent collection
3. **Indexes** keep the dashboard's chip-wide notes summary cheap even when a
   chip has hundreds of thousands of task results.

## Data flow

`NoteService` is the single entry point for every note edit:

```
PUT /chips/{chip}/qubits/{qid}/note
        │
        ▼
NoteService.upsert_qubit_note(...)
        │
        ├─► QubitDocument.find_one(...).save()       # Layer 1: inline
        │
        └─► MongoNoteEventRepository.append(...)     # Layer 2: audit log
```

Same shape for the other six write paths (qubit metric, coupling, coupling
metric, task result — each with upsert + delete).

## Schemas

`NoteModel` is the shared schema for all inline notes:

```python
class NoteModel(BaseModel):
    content: str = ""
    updated_by: str = ""
    updated_at: datetime | None = None
```

`updated_at = None` distinguishes "never noted" from "noted then cleared".

`NoteEventDocument` is the audit row. See [database-structure.md](../reference/database-structure.md#noteeventdocument) for the full field list.

## Endpoints

### Note CRUD

| Method | Path                                                                    | Purpose                                  |
| ------ | ----------------------------------------------------------------------- | ---------------------------------------- |
| PUT    | `/chips/{chip_id}/qubits/{qid}/note`                                    | Upsert qubit's general note              |
| PUT    | `/chips/{chip_id}/qubits/{qid}/metric-notes/{metric_key}`               | Upsert per-metric note on a qubit        |
| PUT    | `/chips/{chip_id}/couplings/{coupling_id}/note`                         | Upsert coupling's general note           |
| PUT    | `/chips/{chip_id}/couplings/{coupling_id}/metric-notes/{metric_key}`    | Upsert per-metric note on a coupling     |
| PUT    | `/task-results/{task_id}/note`                                          | Upsert per-measurement note              |
| DELETE | (same paths)                                                            | Clear the corresponding note             |
| GET    | `/task-results/{task_id}/note`                                          | Fetch a single task-result note          |

DELETE clears the inline note (resets to an empty `NoteModel`) and appends a
`delete` event.

### Aggregation

| Method | Path                                | Purpose                                                |
| ------ | ----------------------------------- | ------------------------------------------------------ |
| GET    | `/chips/{chip_id}/notes-summary`    | One-fetch view: qubit notes + coupling notes + task notes for the chip. Drives the dashboard. |

The summary uses the partial sparse index on `task_result_history.user_note.updated_at` to avoid scanning the full history.

### Knowledge feed

| Method | Path                                              | Purpose                                          |
| ------ | ------------------------------------------------- | ------------------------------------------------ |
| GET    | `/chips/{chip_id}/note-events`                    | Chip-scoped chronological feed                   |
| GET    | `/note-events/by-target?scope=&target_id=`        | Per-target timeline (e.g. all events on Q5)      |
| GET    | `/note-events/search?q=`                          | Full-text search across note contents            |

## Why this works

- **Read latency**: dashboard's primary path (`notes-summary`) hits indexed
  fields only — qubit and coupling collections are bounded in size, and the
  task-result side uses the partial sparse index.
- **Write cost**: each note write is one inline save plus one append. Both are
  sub-millisecond Mongo operations.
- **Auditability**: every state change is an immutable event; nothing is lost.
- **Knowledge enablement**: text-search + per-target timeline open the door for
  LLM context, automated summaries, and cross-chip pattern discovery without
  changing the inline schema.

## Future extensions

- Surface `note-events` in the UI: per-qubit timeline view, search panel.
- Tag / categorize events (NLP-driven labels).
- LLM auto-summarization of recurring annotations.
- Optional retention policy on `note_event` (capped collection or TTL on old
  delete events) once volume warrants it.
