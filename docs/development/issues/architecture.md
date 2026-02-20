# Issues Architecture

## Overview

QDash Issues is a lightweight discussion system attached to task results. It enables experimentalists to leave observations, questions, and discussions directly on calibration results.

- **Root issues** -- Top-level threads with a title, linked to a specific task result.
- **Replies** -- Threaded responses under a root issue.
- **Author actions** -- Edit and delete are restricted to the original author; close/reopen is available to the author and project owner.

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                             │
│                                                                 │
│  ┌─────────────────────┐     ┌──────────────────────────┐      │
│  │ IssuesPage           │     │ IssueDetailPage          │      │
│  │ (useIssues)          │     │ (useIssueReplies)        │      │
│  └────────┬─────────────┘     └────────────┬─────────────┘      │
│           │                               │                     │
│           │ GET /issues                   │ GET  /issues/:id    │
│           │                               │ GET  /issues/:id/   │
│           │                               │       replies       │
│           │                               │ PATCH /issues/:id   │
│           │                               │                     │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ TaskResultDetailPage / TaskResultIssues                │     │
│  │ POST /task-results/:taskId/issues                      │     │
│  └────────────────────────────────────────────────────────┘     │
└───────────┼───────────────────────────────┼─────────────────────┘
            │                               │
┌───────────┼───────────────────────────────┼─────────────────────┐
│  Backend (FastAPI)                                               │
│           │                               │                     │
│  ┌────────▼───────────────────────────────▼──────────────┐      │
│  │  issue router (routers/issue.py)                      │      │
│  │  - CRUD + close/reopen + image upload                 │      │
│  │  - Author-only edit/delete (403)                      │      │
│  └────────┬──────────────────────────────────────────────┘      │
│           │                                                     │
│  ┌────────▼──────────────┐  ┌───────────────────────────┐      │
│  │  IssueDocument        │  │  ISSUES_IMAGE_DIR         │      │
│  │  (MongoDB collection) │  │  (filesystem storage)     │      │
│  └───────────────────────┘  └───────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Responsibility |
|------|---------------|
| `src/qdash/api/routers/issue.py` | FastAPI router: list, get, create, update (PATCH), delete, close/reopen endpoints; image upload/serving |
| `src/qdash/api/schemas/issue.py` | Pydantic schemas: `IssueCreate`, `IssueUpdate`, `IssueResponse`, `ListIssuesResponse` |
| `src/qdash/dbmodel/issue.py` | Bunnet document model: `IssueDocument` with MongoDB indexes |
| `ui/src/hooks/useIssues.ts` | React hooks: `useIssues` (list with pagination/filtering), `useIssueReplies` (replies + CRUD) |
| `ui/src/hooks/useImageUpload.ts` | Image upload hook for drag-and-drop / paste support in MarkdownEditor |
| `ui/src/components/features/issues/IssueDetailPage.tsx` | Issue detail UI: root issue, replies, inline editing, close/reopen |
| `ui/src/components/features/issues/IssuesPage.tsx` | Issue list page with status/task filters and pagination |
| `ui/src/components/features/metrics/TaskResultIssues.tsx` | Issue creation panel embedded in task result detail page |

## Data Model

### IssueDocument (MongoDB)

```python
class IssueDocument(Document):
    project_id: str          # Multi-tenancy key
    task_id: str             # Linked task result
    username: str            # Author
    title: str | None        # Title (root issues only)
    content: str             # Markdown body
    parent_id: str | None    # None = root issue, set = reply
    is_closed: bool          # Thread closed status
    system_info: SystemInfoModel  # created_at, updated_at
```

**Indexes:**
- `(project_id, task_id, system_info.created_at)` -- List issues per task
- `(project_id, parent_id)` -- Fetch replies for a root issue

### API Schemas

| Schema | Purpose |
|--------|---------|
| `IssueCreate` | Create request: `title` (optional), `content`, `parent_id` (optional) |
| `IssueUpdate` | Edit request: `title` (optional, root only), `content` |
| `IssueResponse` | Response: all fields + `created_at`, `updated_at`, `reply_count` |
| `ListIssuesResponse` | Paginated list: `issues[]`, `total`, `skip`, `limit` |

## API Endpoints

| Method | Path | Operation ID | Description |
|--------|------|-------------|-------------|
| `GET` | `/issues` | `listIssues` | List root issues with pagination, filter by `task_id` and `is_closed` |
| `GET` | `/issues/{issue_id}` | `getIssue` | Get a single issue with reply count |
| `GET` | `/issues/{issue_id}/replies` | `getIssueReplies` | List replies for a root issue |
| `PATCH` | `/issues/{issue_id}` | `updateIssue` | Edit content (+ title for root). Author only |
| `DELETE` | `/issues/{issue_id}` | `deleteIssue` | Delete an issue. Author only |
| `PATCH` | `/issues/{issue_id}/close` | `closeIssue` | Close a thread. Author or owner |
| `PATCH` | `/issues/{issue_id}/reopen` | `reopenIssue` | Reopen a thread. Author or owner |
| `POST` | `/task-results/{task_id}/issues` | `createIssue` | Create a root issue or reply |
| `POST` | `/issues/upload-image` | (hidden) | Upload an image attachment |
| `GET` | `/issues/images/{filename}` | (public) | Serve uploaded images |

## Frontend Architecture

### Hooks

**`useIssues()`** -- Used by the issues list page.

- Manages pagination (`skip`, `limit`) and filters (`task_id`, `is_closed`)
- Provides `closeIssue()` / `reopenIssue()` actions
- Auto-invalidates the list query on mutations

**`useIssueReplies(issueId)`** -- Used by the issue detail page.

- Fetches replies for a given root issue
- Provides `addReply()`, `deleteReply()`, `editReply()` actions
- Invalidates both replies and list queries to keep reply counts in sync

### Editing Flow

1. Author clicks the pencil icon next to the issue title (root issue) or reply
2. UI switches to inline editing mode:
   - **Root issue**: title becomes an `<input>` in the header; content becomes a `MarkdownEditor`
   - **Reply**: content becomes a `MarkdownEditor`
3. Save calls `PATCH /issues/{issue_id}` via the generated `useUpdateIssue` mutation
4. Cancel discards local state and exits edit mode
5. `(edited)` badge appears when `updated_at` differs from `created_at` by more than 1 second

### Image Upload

Images can be attached via the MarkdownEditor toolbar, clipboard paste, or drag-and-drop:

1. `useImageUpload` hook calls `POST /issues/upload-image`
2. Server validates type (PNG/JPEG/GIF/WebP) and size (max 5MB)
3. File is stored to `CALIB_DATA_BASE/issues/{uuid}.{ext}`
4. Returns URL as `![image](/api/issues/images/{filename})`
5. Images are served publicly via `GET /issues/images/{filename}`

## Permissions

| Action | Who |
|--------|-----|
| View issues / replies | Any project member |
| Create issue / reply | Any project member |
| Edit issue / reply | Author only |
| Delete issue / reply | Author only |
| Close / Reopen thread | Author or project owner |
