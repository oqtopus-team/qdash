# Collaboration Documents

Documents for users, projects and membership, tags, dashboard notes and their audit log, and the forum.

Collections overview: [Database Structure](./database-structure.md).

## ProjectDocument

**Collection:** `project`

**Indexes:**

- `project_id` - Unique identifier per project
- `(owner_user_id, name)` - Efficient owner lookup by immutable user ID
- `(owner_username, name)` - Prevent duplicate names per owner

```python
class ProjectDocument(Document):
    project_id: str            # UUID/slug
    owner_user_id: str         # Immutable internal owner ID
    owner_username: str
    name: str
    description: str | None = None
    tags: list[str] = []
    system_info: SystemInfoModel
```

---

## ProjectMembershipDocument

**Collection:** `project_membership`

**Indexes:**

- `(project_id, username)` - Unique membership per user/project
- `(project_id, user_id)` - Membership lookup by immutable user ID
- `(user_id, status)` - Efficient active membership lookup
- `(username, status)` - Efficient lookup of invitations

```python
class ProjectMembershipDocument(Document):
    project_id: str
    user_id: str
    username: str
    role: ProjectRole
    status: Literal["pending", "active", "revoked"] = "pending"
    invited_by_user_id: str | None = None
    invited_by: str | None = None
    last_accessed_at: str | None = None
    system_info: SystemInfoModel
```

---

## UserDocument

**Collection:** `user`

**Indexes:**

- `username` - Unique index
- `user_id` - Unique immutable internal identifier
- `access_token` - Unique index

```python
class UserDocument(Document):
    user_id: str
    username: str
    hashed_password: str
    access_token: str
    default_project_id: str | None = None
    full_name: str | None = None
    disabled: bool = False
    system_info: SystemInfoModel
```

---

## TagDocument

**Collection:** `tag`

**Indexes:**

- `(project_id, name)` - Unique compound index

```python
class TagDocument(Document):
    project_id: str
    username: str
    name: str
```

---

## MetricNoteDocument

**Collection:** `metric_note`

Stores the current dashboard metric note for one qubit/coupling metric in one operational scope. This collection supports both teams that manage explicit cool-down IDs and teams that only work from time ranges.

**Indexes:**

- `(project_id, chip_id, target_type, target_id, metric_key, scope_key)` - Unique current note per target metric and scope
- `(project_id, chip_id, scope_key, target_type, target_id)` - Dashboard notes summary
- `(project_id, chip_id, scope_started_at, scope_ended_at)` - Time-range fallback when cool-down docs are added later

```python
class MetricNoteDocument(Document):
    project_id: str
    chip_id: str
    target_type: str                 # "qubit" | "coupling"
    target_id: str                   # qid or coupling id
    metric_key: str
    note: NoteModel

    scope_type: str                  # "cooldown" | "time_range" | "global"
    scope_key: str                   # "cooldown:<id>", "time_range:<start>:<end>", or "global"
    cooldown_id: str | None
    scope_started_at: datetime | None
    scope_ended_at: datetime | None
    scope_source: str                # explicit_cooldown, current_cooldown, inferred_from_range, manual_time_range, legacy_global
    system_info: SystemInfoModel
```

When a cool-down ID is known, the note stores both `cooldown_id` and the cool-down time bounds. When no cool-down document exists, the dashboard can save a `time_range` note. If a cool-down document is added later, summary reads include matching time-range notes inside that cool-down until they are edited into the explicit cool-down scope.

---

## ChipNoteDocument

**Collection:** `chip_note`

Stores the current dashboard chip note in one operational scope. This is the writable dashboard chip-note store; the legacy global note remains on `ChipDocument.note`.

**Indexes:**

- `(project_id, chip_id, scope_key)` - Unique current chip note per scope
- `(project_id, chip_id, scope_started_at, scope_ended_at)` - Time-range fallback when cool-down docs are added later

```python
class ChipNoteDocument(Document):
    project_id: str
    chip_id: str
    note: NoteModel

    scope_type: str                  # "cooldown" | "time_range" | "global"
    scope_key: str                   # "cooldown:<id>", "time_range:<start>:<end>", or "global"
    cooldown_id: str | None
    scope_started_at: datetime | None
    scope_ended_at: datetime | None
    scope_source: str
    system_info: SystemInfoModel
```

When the dashboard has a selected cool-down, chip notes are stored under `scope_key = "cooldown:<id>"`, so each cool-down can carry a different chip-level summary.

---

## TargetNoteDocument

**Collection:** `target_note`

Stores the current dashboard pinned summary for one qubit/coupling target in one operational scope. This is the writable dashboard summary-note store; legacy global notes remain on `QubitDocument.note` and `CouplingDocument.note`.

**Indexes:**

- `(project_id, chip_id, target_type, target_id, scope_key)` - Unique current summary per target and scope
- `(project_id, chip_id, scope_key, target_type, target_id)` - Dashboard notes summary
- `(project_id, chip_id, scope_started_at, scope_ended_at)` - Time-range fallback when cool-down docs are added later

```python
class TargetNoteDocument(Document):
    project_id: str
    chip_id: str
    target_type: str                 # "qubit" | "coupling"
    target_id: str                   # qid or coupling id
    note: NoteModel

    scope_type: str                  # "cooldown" | "time_range" | "global"
    scope_key: str                   # "cooldown:<id>", "time_range:<start>:<end>", or "global"
    cooldown_id: str | None
    scope_started_at: datetime | None
    scope_ended_at: datetime | None
    scope_source: str
    system_info: SystemInfoModel
```

For `time_range` summary reads, notes are matched by **window overlap** rather than by an exact `scope_key`. The dashboard's default range is relative to "now", so its bounds drift by seconds/minutes between writing a note and reading it back; matching any `time_range` note whose `[scope_started_at, scope_ended_at]` window overlaps the requested window keeps those notes visible (issue #1109). When several overlapping notes exist for the same target metric, the one whose `scope_key` matches the request exactly wins, otherwise the most recently edited note is shown.

---

## NoteEventDocument

**Collection:** `note_event`

Append-only audit log. The `NoteService` writes one row here on every
upsert/delete of a note (qubit, qubit metric, coupling, coupling metric, task
result). Used for: edit history, per-target timeline, full-text search across
all notes (knowledge view, LLM context).

**Indexes:**

- `(project_id, chip_id, created_at DESC)` - Chip-scoped chronological feed.
- `(project_id, scope, target_id, created_at DESC)` - Per-target timeline.
- `text(content)` - Full-text search across note contents within a project.

```python
class NoteEventDocument(Document):
    project_id: str
    chip_id: str
    scope: str           # qubit | qubit_metric | coupling | coupling_metric | task_result
    target_id: str       # qid for qubit/qubit_metric, coupling_id, or task_id
    metric_key: str = "" # only set for *_metric scopes
    action: str          # upsert | delete
    actor: str           # username
    content: str = ""    # Note content at time of action ("" for delete)
    extra: dict[str, str] = {}  # e.g. {"qid": "5", "task_name": "T1"}
    created_at: datetime
```

The collection is **never updated in place** — every entry is a new
immutable event. Two read patterns are exposed:

- `GET /chips/{chip_id}/note-events` (chip timeline)
- `GET /note-events/by-target?scope=&target_id=` (per-target timeline)
- `GET /note-events/search?q=` (cross-chip text search)

---

## ForumLabelDocument

Custom, project-scoped forum labels, similar to GitHub issue labels. Each label key set by a
client must exist as a `ForumLabelDocument` for the project. Label keys stored on threads without a
definition are omitted from API responses and dropped the next time the thread's labels are updated.

New projects start with no labels; owners and editors create them as needed.

> **Warning:** `migrate-forum-status` is a one-time legacy migration. It collapses every label to
> `review`/`anomaly` and keeps only one label per thread, so do not re-run it once custom labels are
> in use.

Collection: `forum_label`

```python
class ForumLabelDocument(Document):
    project_id: str
    key: str              # Stable label key, e.g. "review".
                           # Server-generated from name; never set by the client.
    name: str              # Display name
    description: str = ""
    color: str             # Lowercase hex color, e.g. "#3b82f6"
    system_info: SystemInfoModel
```

---

## SlackForumThreadDocument

Tracks the Slack message posted for each root forum thread, enabling reply and status-change notifications to appear in the same Slack thread.

Collection: `slack_forum_thread`

```python
class SlackForumThreadDocument(Document):
    post_id: str          # Forum root post ObjectId (unique)
    project_id: str
    channel_id: str       # Slack channel where the message was posted
    message_ts: str       # Slack message timestamp (used as thread_ts for replies)
    system_info: SystemInfoModel
```
