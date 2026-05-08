# Cryostats & Cool-downs

The `/cryo` page lets you track cryostats (dilution refrigerators) and their
cool-down cycles, then assign chips to them so calibration data is
automatically tagged with the cool-down it ran in.

## Concepts

| Concept       | What it is                                                                                                  |
| ------------- | ----------------------------------------------------------------------------------------------------------- |
| **Cryostat**  | A long-lived piece of lab hardware (e.g. `K-101`). One row per physical fridge.                             |
| **Cool-down** | A single cool-down / warm-up cycle of a cryostat (e.g. `2026-001`). A fridge will have many over time.     |
| **Chip**      | The quantum chip loaded into a cool-down. Carries a `current_cooldown_id` while loaded.                     |

The relationship: **Cryostat ─< Cool-down ─< Chip** (many-to-one-to-many — multiple chips can live in the same cool-down).

## Workflow

### 1. Register a cryostat

Open `/cryo` → **New cryostat** → set:
- `Cryo ID` (project-unique short code, e.g. `K-101`)
- `Name` (display label)
- `Location`

### 2. Open a cool-down

Inside the cryostat card → **New cool-down** → set just the **Cooldown ID** (project-unique, e.g. `2026-001`).

The cool-down is created with `started_at = now()` and `ended_at = null` (active). Edit dates, description, and load chips from the detail panel.

For a **past** cool-down, create with the ID, then in the detail panel click **edit dates** to set started/ended in the past and add chips. The dashboard's cool-down filter then restricts data by the cool-down's date range — past data does not need to be re-tagged. Newly-written calibration data is automatically tagged with `cooldown_id` for any chip currently loaded.

### 3. Load chips

Inside the cool-down row → **Add chip…** dropdown → pick a chip.

This:
- Adds the chip to `cooldown.chip_ids`
- Sets the chip's `current_cooldown_id` to this cool-down (if active)

From this moment on, every task result, qubit history snapshot, and coupling
history snapshot the workflow writes carries this `cooldown_id` denormalized.

### 4. End a cool-down (warm-up)

Click **End** on an active cool-down. This:
- Sets `ended_at = now()`
- Clears `chip.current_cooldown_id` for every chip that was pointing at this cool-down

Subsequent calibration writes will have an empty `cooldown_id`.

## Wiring info

Each cool-down has a **Wiring info** section in its detail panel for recording
how the fridge was wired up for that cycle (MUX assignments, attenuation,
filters, diagrams, etc.). The editor is a Notion-style block editor that is
**always editable** — there is no separate edit/view toggle, and changes save
automatically (~1 s after you stop typing). A subtle *Saving… / Saved · Xs
ago* indicator at the top-right of the section shows the autosave status.

- Type <kbd>/</kbd> to insert a block: **table**, image, heading, bullet /
  numbered / check list, toggle, quote, code, divider.
- **Tables**: hover a row or column edge to add or delete; drag edges to
  resize. Right-click a cell for the cell menu.
- **Images**: paste a screenshot with <kbd>⌘/Ctrl+V</kbd>, drag a file in, or
  insert via the slash menu. Images are embedded inline as base64; max 5 MB
  per image to keep cool-down documents within Mongo's 16 MiB limit.
- Drag the <kbd>⠿</kbd> handle in the left margin to reorder blocks.
- Existing Markdown notes are imported automatically the first time the
  section is opened.
- Each save persists both the rich block representation (authoritative) and a
  Markdown export (for fallback rendering and search).

### Wiring history (checkpoints)

Autosave keeps the *current* wiring up to date but does not preserve a
history. When the wiring actually changes during a cool-down (e.g. a MUX line
is swapped, attenuators are added), record a **checkpoint**:

1. Below the editor, click **Save checkpoint**.
2. Briefly describe what changed (required, e.g. *"Swapped MUX line on Q3
   readout after warm-up"*) and confirm.

Each checkpoint captures the actor, the comment, and a Markdown snapshot of
the wiring at that moment. Checkpoints appear in the **Wiring history** list
underneath the editor — click an entry to expand it and view the snapshot.
Snapshots are append-only, so you can always trace which configuration
produced which calibration data within the same cool-down.

## Filtering by cool-down

The dashboard's filter bar shows a **Cool-down…** dropdown next to the chip
selector once chips are assigned to one or more cool-downs. Picking a cool-down
sets the dashboard's date range to the cool-down's `started_at..ended_at`
(falling back to today for active cool-downs). This is a time-range filter, so
historical data written before the cool-down was registered is included
automatically as long as it falls inside the cool-down's date span.

Newly-written calibration data is also tagged with `cooldown_id` directly via
the chip's `current_cooldown_id`, so a future indexed-filter switch can use
that tag without changing past data.
