# Dashboard

The `/dashboard` page is the at-a-glance view of a chip's calibration health. It shows every metric on a single page — heatmap + per-metric CDF — and lets you leave free-form notes anywhere it makes sense.

## What's on the page

From top to bottom:

1. **Filter bar** — chip selector, time range (relative / absolute), selection mode (latest / best / average).
2. **Notes summary** — every note attached to this chip in one place, grouped by qubit / coupling and by experiment (task result).
3. **All metrics summary table** (collapsed by default) — coverage / median / min / max for every metric in the active time range.
4. **Qubit Metrics** — one row per metric, with the topology heatmap (2/3 width) and its CDF chart (1/3 width).
5. **Coupling Metrics** — same layout, coupling chips on the left, CDF on the right.

Each per-metric section also carries its own coverage gauge.

## Notes

QDash supports six levels of notes, all sharing the same `NoteModel` schema (`content`, `updated_by`, `updated_at`):

| Scope                 | Where it lives                       | When to use                                                              |
| --------------------- | ------------------------------------ | ------------------------------------------------------------------------ |
| **Qubit summary**     | `TargetNoteDocument` / `QubitDocument.note` | Pinned target summary for the selected cool-down or time range; legacy global notes fall back to `QubitDocument.note` |
| **Qubit + Metric**    | `MetricNoteDocument`                 | Legacy per-metric notes shown read-only in the dashboard                 |
| **Coupling summary**  | `TargetNoteDocument` / `CouplingDocument.note` | Pinned target summary for the selected cool-down or time range; legacy global notes fall back to `CouplingDocument.note` |
| **Coupling + Metric** | `MetricNoteDocument`                 | Legacy per-metric notes shown read-only in the dashboard                 |
| **Task Result**       | `TaskResultHistoryDocument.user_note`| Notes about this specific measurement (anomaly, parameter intent)        |
| **Chip**              | `ChipNoteDocument` / `ChipDocument.note` | Chip-level summary for the selected cool-down or time range; legacy global notes remain on `ChipDocument.note` |

### How to write a note

- Edit **Chip note** above Target Summaries to record chip-level context for the selected cool-down or time range.
- Click any qubit cell or coupling chip on a metric → opens the metric history modal.
  - The side panel shows / lets you edit the **pinned target summary** for the selected cool-down or time range.
  - The body of the modal includes a **Note** section (above issues) for the **task result** currently selected.
- Cells with an existing note show a sticky-note icon. A faint outlined icon indicates a note exists on **another** metric for the same qubit.
- Hovering a cell reveals a tooltip listing **all notes on that target across metrics**, plus the value and unit.

### Notes visibility

- The notes summary at the top of the dashboard is the canonical "what's been written" view for the current cool-down or selected time range. Click any target summary or legacy per-metric note row to jump to the relevant dashboard modal; click any task-result note to open the task result detail page.
- Notes are shared within a project (no per-user filtering). The `updated_by` field tracks the last editor.

### Target summary scoping

Dashboard pinned target summaries are scoped by the operational context:

- If a cool-down is explicitly selected, summaries are saved under that `cooldown_id`.
- If no cool-down is selected, summaries use the current dashboard `start_at` / `end_at` range.
- If the selected time range matches a single cool-down document, QDash stores the summary in that cool-down scope.
- Existing global chip, qubit, and coupling notes remain available as legacy fallback when no operational scope is selected.
- Per-metric notes are legacy read-only dashboard context; use pinned summaries or forum discussions for new notes.

## Knowledge feed

Every note edit (upsert / delete) appends a row to the immutable `note_event` collection. This drives:

- Per-chip annotation timeline: `GET /chips/{chip_id}/note-events`
- Per-target timeline (e.g. all events on Q5): `GET /note-events/by-target?scope=qubit&target_id=5`
- Cross-chip text search: `GET /note-events/search?q=unstable`

Use these for retrospective audits, knowledge mining, or feeding LLM contexts. The current dashboard does not yet surface a UI for these endpoints — they are available for future work and external integrations.

## Performance

- The dashboard fetches all notes via `GET /chips/{chip_id}/notes-summary`, a single query that joins inline notes from `qubit`, `coupling`, and (filtered) `task_result_history`.
- A partial sparse index on `task_result_history.user_note.updated_at` ensures the summary scans only annotated rows, even when the chip has hundreds of thousands of task results.
