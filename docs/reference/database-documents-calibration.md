# Calibration Documents

Documents that hold a chip's accepted calibration values, their daily snapshots, task and backend definitions, and the cryostat cool-downs that give measurements their physical context.

Collections overview: [Database Structure](./database-structure.md).

## ChipDocument

**Collection:** `chip`

**Indexes:**

- `(project_id, chip_id)` - Unique compound index
- `(username, chip_id)` - Backward-compat lookup while migrating

```python
class ChipDocument(Document):
    project_id: str
    username: str                # Creator/owner username
    chip_id: str = "SAMPLE"
    size: int = 64
    current_cooldown_id: str | None = None  # Cool-down the chip is currently loaded in
    qubits: dict[str, QubitModel] = {}
    couplings: dict[str, CouplingModel] = {}
    installed_at: str  # ISO8601
    note: NoteModel              # Legacy global chip note
    system_info: SystemInfoModel
```

**Editable via** `PATCH /chips/{chip_id}` (topology_id, legacy global note). Dashboard-scoped chip notes are edited via `GET/PUT/DELETE /chips/{chip_id}/note` with `cooldown_id` or a time range. **Deletable via** `DELETE /chips/{chip_id}` (refuses if qubits/couplings exist; `?force=true` cascades). Use `GET /chips/{chip_id}/deletion-impact` for a preflight count before deleting.

**Key Methods:**

- `get_current_chip(project_id)` - Get the most recently installed chip per project
- `get_chip_by_id(project_id, chip_id)` - Get a specific chip
- `update_qubit(qid, qubit_data)` - Update a qubit
- `update_coupling(qid, coupling_data)` - Update a coupling

---

## QubitDocument

**Collection:** `qubit`

**Indexes:**

- `(project_id, chip_id, qid)` - Unique compound index
- `(project_id, username)` - Filter by project/member

```python
class QubitDocument(Document):
    project_id: str
    username: str
    qid: str
    status: str = "pending"
    chip_id: str
    data: dict
    note: NoteModel = NoteModel()                  # Free-form per-qubit note
    metric_notes: dict[str, NoteModel] = {}        # Legacy global per-metric notes
    system_info: SystemInfoModel
```

**Key Methods:**

- `update_calib_data(username, qid, chip_id, output_parameters)` - Update calibration data
- `update_status(qid, chip_id, status)` - Update status

**Note Fields:**

- `note` - Legacy global free-form note about the qubit itself. Scoped dashboard pinned summaries are stored in `TargetNoteDocument` when `PUT /chips/{chip}/qubits/{qid}/note` includes `cooldown_id` or a time range.
- `metric_notes[metric_key]` - Legacy global per-metric annotations. Existing scoped per-metric notes are stored in `MetricNoteDocument`; new dashboard notes should use pinned summaries or forum discussions.

---

## CouplingDocument

**Collection:** `coupling`

**Indexes:**

- `(project_id, chip_id, qid)` - Unique compound index
- `(project_id, username)` - Filter by project/member

```python
class CouplingDocument(Document):
    project_id: str
    username: str
    qid: str               # Coupling ID (e.g., "0-1")
    status: str = "pending"
    chip_id: str
    data: dict
    note: NoteModel = NoteModel()                  # Free-form per-coupling note
    metric_notes: dict[str, NoteModel] = {}        # Legacy global per-metric notes
    system_info: SystemInfoModel
```

**Note Fields:**

- `note` - Legacy global free-form note about the coupling. Scoped dashboard pinned summaries are stored in `TargetNoteDocument` when `PUT /chips/{chip}/couplings/{coupling_id}/note` includes `cooldown_id` or a time range.
- `metric_notes[metric_key]` - Legacy global per-metric annotations. Existing scoped per-metric notes are stored in `MetricNoteDocument`; new dashboard notes should use pinned summaries or forum discussions.

---

## QubitHistoryDocument

**Collection:** `qubit_history`

**Indexes:**

- `(project_id, chip_id, qid, recorded_date)` - Unique compound index

Daily snapshot history table.

```python
class QubitHistoryDocument(Document):
    project_id: str
    username: str
    qid: str
    status: str
    chip_id: str
    data: dict
    system_info: SystemInfoModel
    recorded_date: str  # YYYYMMDD format
```

---

## ChipHistoryDocument

**Collection:** `chip_history`

**Indexes:**

- `(project_id, chip_id, recorded_date)` - Unique compound index

```python
class ChipHistoryDocument(Document):
    project_id: str
    chip_id: str
    username: str
    size: int
    qubits: dict[str, QubitModel]
    couplings: dict[str, CouplingModel]
    installed_at: str
    system_info: SystemInfoModel
    recorded_date: str  # YYYYMMDD format
```

---

## CouplingHistoryDocument

**Collection:** `coupling_history`

**Indexes:**

- `(project_id, chip_id, qid, recorded_date)` - Unique compound index

```python
class CouplingHistoryDocument(Document):
    project_id: str
    username: str
    qid: str
    status: str
    chip_id: str
    data: dict
    system_info: SystemInfoModel
    recorded_date: str  # YYYYMMDD format
```

---

## TaskDocument

**Collection:** `task`

**Indexes:**

- `(project_id, name)` - Unique compound index
- `(project_id, task_type)` - Filter by scope

Stores task definition information.

```python
class TaskDocument(Document):
    project_id: str
    username: str
    name: str              # Task name (e.g., "CheckT1")
    backend: str | None
    description: str
    task_type: str         # "global", "qubit", "coupling"
    input_parameters: dict | None
    output_parameters: dict | None
```

---

## BackendDocument

**Collection:** `backend`

**Indexes:**

- `(project_id, name)` - Unique compound index

```python
class BackendDocument(Document):
    project_id: str
    username: str
    name: str
    system_info: SystemInfoModel
```

---

## CryostatDocument

**Collection:** `cryostat`

A long-lived piece of lab hardware (dilution refrigerator). Cool-downs reference this entity via ``cryo_id``.

**Indexes:**

- `(project_id, cryo_id)` - Unique compound index

```python
class CryostatDocument(Document):
    project_id: str
    cryo_id: str                 # Project-unique (e.g. "K-101")
    name: str = ""
    manufacturer: str = ""
    model: str = ""
    location: str = ""
    status: str = "active"       # active | maintenance | decommissioned
    commissioned_at: datetime | None = None
    decommissioned_at: datetime | None = None
    note: NoteModel              # Free-form note (shared NoteModel)
    system_info: SystemInfoModel
```

CRUD endpoints under `/cryostats`. The `/cryo` UI page manages these.

---

## CooldownDocument

**Collection:** `cooldown`

One cool-down / warm-up cycle of one cryostat. The cool-down's `cooldown_id` is denormalized onto every task result, qubit history, and coupling history written while the chip is loaded into the cool-down — see [history denormalization](#history-denormalization-of-cooldown-id) below.

**Indexes:**

- `(project_id, cooldown_id)` - Unique compound index
- `(project_id, cryo_id, started_at DESC)` - Cool-downs by cryostat (newest first)
- `(project_id, chip_ids, started_at DESC)` - Cool-downs containing a chip
- `(project_id, started_at DESC)` - Project-wide chronological list

```python
class CooldownDocument(Document):
    project_id: str
    cooldown_id: str             # Project-unique (e.g. "2026-001")
    cryo_id: str                 # Owning cryostat
    description: str = ""
    started_at: datetime
    ended_at: datetime | None = None  # None = ongoing
    chip_ids: list[str] = []     # Chips loaded into this cool-down
    note: NoteModel
    system_info: SystemInfoModel
```

CRUD endpoints under `/cooldowns`. Chip assignment via:

- `POST /cooldowns/{cooldown_id}/chips/{chip_id}` — assign (also sets `chip.current_cooldown_id` if the cool-down is active)
- `DELETE /cooldowns/{cooldown_id}/chips/{chip_id}` — unassign (also clears `chip.current_cooldown_id` if it pointed here)

### History denormalization of `cooldown_id`

When the workflow persists calibration data, the chip's `current_cooldown_id` is copied at write time onto:

- `TaskResultHistoryDocument.cooldown_id`
- `QubitHistoryDocument.cooldown_id`
- `CouplingHistoryDocument.cooldown_id`

This lets dashboards and metrics queries filter "show me only data from cool-down 2026-001" with a direct indexed lookup, instead of joining on time ranges.

A partial sparse index `(project_id, cooldown_id, start_at DESC)` on `task_result_history` ensures that cool-down filters scan only annotated rows.
