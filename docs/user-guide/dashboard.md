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

QDash supports five levels of notes, all sharing the same `NoteModel` schema (`content`, `updated_by`, `updated_at`):

| Scope                 | Where it lives                       | When to use                                                              |
| --------------------- | ------------------------------------ | ------------------------------------------------------------------------ |
| **Qubit (general)**   | `QubitDocument.note`                 | Intrinsic facts about the qubit (used in paper X, replaced 2026-04-15)   |
| **Qubit + Metric**    | `MetricNoteDocument`                 | Notes specific to a metric on this qubit in the selected cool-down or time range |
| **Coupling (general)**| `CouplingDocument.note`              | Intrinsic facts about the coupling (MUX-bridging, high crosstalk)        |
| **Coupling + Metric** | `MetricNoteDocument`                 | Per-metric notes on a coupling in the selected cool-down or time range   |
| **Task Result**       | `TaskResultHistoryDocument.user_note`| Notes about this specific measurement (anomaly, parameter intent)        |
| **Chip**              | `ChipDocument.note`                  | Permanent chip-level context such as serial number, fabrication batch, or shared caveats |

### How to write a note

- Click **Chip note** in the dashboard filters to edit permanent chip-level context.
- Click any qubit cell or coupling chip on a metric → opens the metric history modal.
  - The side panel shows / lets you edit the **per-(target, metric) note** for the selected cool-down or time range.
  - The body of the modal includes a **Note** section (above issues) for the **task result** currently selected.
- Cells with an existing note show a sticky-note icon. A faint outlined icon indicates a note exists on **another** metric for the same qubit.
- Hovering a cell reveals a tooltip listing **all notes on that target across metrics**, plus the value and unit.

### Notes visibility

- The notes summary at the top of the dashboard is the canonical "what's been written" view for the current cool-down or selected time range. Click any per-metric note row to jump to the metric modal; click any task-result note to open the task result detail page.
- Notes are shared within a project (no per-user filtering). The `updated_by` field tracks the last editor.

### Metric note scoping

Dashboard metric notes are scoped by the operational context:

- If a cool-down is explicitly selected, notes are saved under that `cooldown_id`.
- If no cool-down is selected, notes use the current dashboard `start_at` / `end_at` range.
- If the selected time range matches a single cool-down document, QDash stores the note in that cool-down scope.
- If a cool-down document is added later, matching time-range notes remain visible in that cool-down's summary until they are edited into the explicit cool-down scope.

## Knowledge feed

Every note edit (upsert / delete) appends a row to the immutable `note_event` collection. This drives:

- Per-chip annotation timeline: `GET /chips/{chip_id}/note-events`
- Per-target timeline (e.g. all events on Q5): `GET /note-events/by-target?scope=qubit&target_id=5`
- Cross-chip text search: `GET /note-events/search?q=unstable`

Use these for retrospective audits, knowledge mining, or feeding LLM contexts. The current dashboard does not yet surface a UI for these endpoints — they are available for future work and external integrations.

## Performance

- The dashboard fetches all notes via `GET /chips/{chip_id}/notes-summary`, a single query that joins inline notes from `qubit`, `coupling`, and (filtered) `task_result_history`.
- A partial sparse index on `task_result_history.user_note.updated_at` ensures the summary scans only annotated rows, even when the chip has hundreds of thousands of task results.
