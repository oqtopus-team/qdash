# Task Editor Design Document

## Overview

This document describes the design and implementation plan for the Task Editor feature in QDash. The Task Editor will provide a UI interface to view and edit task implementation code (Python files under `src/qdash/workflow/tasks/`), similar to the existing Files Editor for configuration files.

## Background

### Current State

**Tasks Page (`/ui/src/app/tasks/page.tsx`)**

- Displays task metadata: name, description, task_type, input/output parameters
- Data source: `/api/task` endpoint (fetches from TaskDocument in MongoDB)
- UI features: Grid/List view toggle, detail modal
- **Limitation**: Shows only parameter definitions, not actual implementation code

**Actual Task Implementation (`src/qdash/workflow/tasks/`)**

- Python classes inheriting from `BaseTask`
- Contains rich information:
  - `preprocess()`, `postprocess()`, `run()`, `batch_run()` method implementations
  - Parameter conversion and validation logic
  - R2 thresholds, timeout settings
  - Actual measurement/calculation algorithms
- File structure:
  ```
  src/qdash/workflow/tasks/
  ├── base.py                    # BaseTask definition
  ├── active_protocols.py        # Task instance generator
  ├── qubex/                     # qubex backend
  │   ├── base.py
  │   ├── one_qubit_coarse/     # 16 files
  │   ├── one_qubit_fine/       # 4 files
  │   ├── two_qubit/            # 5 files
  │   ├── measurement/
  │   ├── benchmark/
  │   ├── system/
  │   ├── box_setup/
  │   └── cw/
  └── fake/                      # fake backend for testing
  ```

**Files Editor (`/ui/src/app/files/page.tsx`)**

- Monaco Editor with syntax highlighting
- File tree navigation
- Edit functionality with lock/unlock mechanism
- Git integration (pull/push)
- Target: Configuration files (`config/qubex/`)

### Problem Statement

Users currently have **limited visibility** into task implementations:

- Can only see parameter definitions (metadata)
- Cannot understand the actual algorithm logic
- Difficult to debug or troubleshoot calibration issues
- No way to view preprocessing/postprocessing logic

## Proposal: Task Editor Feature

### Benefits

1. **Increased Information Transparency**
   - Current: Parameter definitions only → Proposed: Full implementation code visibility
   - Better understanding of calibration algorithms
   - Easier debugging and troubleshooting

2. **Improved Developer Experience**
   - View/edit task implementations directly from UI
   - Git-based version control
   - Monaco Editor for comfortable coding experience

3. **Consistent UX**
   - Unified interface between Files Editor and Task Editor
   - Reduced learning curve

### Security & Safety Considerations

1. **Code Execution Risk**
   - Direct task code editing affects workflow execution
   - **Mitigation**: Lock mechanism (same as Files Editor)

2. **Read-Only Mode**
   - Production environments should use `read_only: true`
   - Prevents accidental modifications

3. **Git-Based Workflow**
   - All changes tracked via Git
   - Pull request review process recommended

## Design

### Implementation Approach: Option A (Recommended)

**Extend Existing Tasks Page**

- Maintain current metadata view (Grid/List)
- Add "View Code" button to each task card
- Click to open Monaco Editor modal or separate tab
- Reuse Files Editor components (DRY principle)

### Alternative: Option B

**Dedicated Task Editor Page**

- Create `/tasks/editor` as independent page
- Same layout as Files Editor
- Task-specific features (parameter highlighting, doc generation)

**Recommendation**: Option A is more practical for phased implementation.

## Configuration Management

### Current Configuration Strategy

QDash uses a **hybrid approach** for configuration management:

| Configuration Type       | Storage | Git Managed | Edit Method | Example Use Cases                 |
| ------------------------ | ------- | ----------- | ----------- | --------------------------------- |
| **Environment-specific** | `.env`  | ❌          | Manual edit | Ports, credentials, API keys      |
| **Application settings** | YAML    | ✅          | UI Editor   | Metrics definitions, chip configs |

### Rationale

**Security**

- `.env`: Contains secrets (passwords, API keys) → Never commit to Git
- YAML: Public settings → Safe to version control

**Portability**

- `.env`: Different values per environment (dev/staging/prod)
- YAML: Shared across all environments

**Version Control**

- YAML: Track configuration change history
- Critical for chip settings rollback and diff review

**UI Editing**

- Files Editor already supports YAML editing
- Git integration (pull/push) implemented

### Task Editor Configuration

#### Recommended: Hybrid Approach

**Environment Variable (`.env`)**

```bash
# Task Editor paths
TASK_BASE_PATH="./src/qdash/workflow/tasks"
```

**Application Configuration (`config/qdash.yaml`)**

```yaml
# QDash Application Configuration
app:
  name: "QDash"
  version: "1.0.0"

# Task Editor configuration
task_editor:
  enabled: true
  read_only: false # Set to true in production

  # Backend-specific settings
  backends:
    qubex:
      categories:
        - one_qubit_coarse
        - one_qubit_fine
        - two_qubit
        - measurement
        - benchmark
        - system
    fake:
      categories: []

# Files Editor configuration (existing)
files_editor:
  enabled: true
  base_path: "config/qubex" # Equivalent to CONFIG_PATH
  git_enabled: true

# UI feature flags
ui:
  features:
    task_editor: true
    python_flow_editor: true
    slack_agent: true
```

#### Why This Approach?

1. **Separation of Concerns**
   - `.env`: Environment-specific paths
   - YAML: Application behavior and feature flags

2. **Read-Only Control**
   - `read_only: false` in development
   - `read_only: true` in production (prevent accidental edits)

3. **Feature Flags**
   - Easily enable/disable Task Editor per environment
   - Centralized UI feature management

## Technical Implementation

### Backend API

#### New Endpoints

**File Path**: `src/qdash/api/routers/task.py`

```python
import os
from pathlib import Path
from fastapi import HTTPException, Query
from pydantic import BaseModel

# Get task base path from environment
TASK_BASE_PATH = Path(os.getenv("TASK_BASE_PATH", "./src/qdash/workflow/tasks"))

# Docker environment support
if Path("/app").exists() and not TASK_BASE_PATH.is_absolute():
    TASK_BASE_PATH = Path("/app") / "src" / "qdash" / "workflow" / "tasks"


class TaskFileTreeNode(BaseModel):
    """Task file tree node model."""

    name: str
    path: str  # Relative path from TASK_BASE_PATH
    type: str  # "file" or "directory"
    backend: str | None = None  # "qubex", "fake", etc.
    category: str | None = None  # "one_qubit_coarse", etc.
    children: list["TaskFileTreeNode"] | None = None


class SaveTaskFileRequest(BaseModel):
    """Request model for saving task file."""

    path: str  # Relative path from TASK_BASE_PATH
    content: str


@router.get(
    "/tasks/files/tree",
    response_model=list[TaskFileTreeNode],
    summary="Get task file tree",
    operation_id="get_task_file_tree",
)
def get_task_file_tree(
    current_user: Annotated[User, Depends(get_current_active_user)],
    backend: str | None = Query(None, description="Filter by backend"),
) -> list[TaskFileTreeNode]:
    """Get file tree for task implementations.

    Returns task files organized by backend and category.
    """
    return build_task_file_tree(TASK_BASE_PATH, backend_filter=backend)


@router.get(
    "/tasks/files/content",
    summary="Get task file content",
    operation_id="get_task_file_content",
)
def get_task_file_content(
    current_user: Annotated[User, Depends(get_current_active_user)],
    path: str = Query(..., description="Relative path from TASK_BASE_PATH"),
) -> dict:
    """Get content of a task file."""
    file_path = validate_task_file_path(path)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    with open(file_path, "r") as f:
        content = f.read()

    return {
        "path": path,
        "content": content,
        "language": "python",
        "read_only": load_task_editor_config().read_only,
    }


@router.post(
    "/tasks/files/save",
    summary="Save task file content",
    operation_id="save_task_file_content",
)
def save_task_file_content(
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: SaveTaskFileRequest,
) -> dict:
    """Save task file content (if editing is enabled)."""
    config = load_task_editor_config()

    if config.read_only:
        raise HTTPException(
            status_code=403,
            detail="Task editing is disabled (read_only mode)"
        )

    file_path = validate_task_file_path(request.path)

    # Validate Python syntax
    try:
        compile(request.content, file_path.name, 'exec')
    except SyntaxError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Python syntax error: {e}"
        )

    with open(file_path, "w") as f:
        f.write(request.content)

    return {"message": "File saved successfully", "path": request.path}


def validate_task_file_path(relative_path: str) -> Path:
    """Validate relative_path to prevent path traversal attacks.

    Args:
        relative_path: Relative path from TASK_BASE_PATH

    Returns:
        Resolved absolute path

    Raises:
        HTTPException: If validation fails
    """
    # Prevent path traversal
    if ".." in relative_path:
        raise HTTPException(status_code=400, detail="Path traversal detected")

    target_path = TASK_BASE_PATH / relative_path
    resolved_path = target_path.resolve()

    # Ensure resolved path is within TASK_BASE_PATH
    if not str(resolved_path).startswith(str(TASK_BASE_PATH.resolve())):
        raise HTTPException(status_code=400, detail="Path outside task directory")

    return resolved_path


def build_task_file_tree(
    directory: Path,
    base_path: Path = TASK_BASE_PATH,
    backend_filter: str | None = None
) -> list[TaskFileTreeNode]:
    """Build file tree structure recursively.

    Args:
        directory: Directory to scan
        base_path: Base path for relative path calculation
        backend_filter: Optional backend name to filter by

    Returns:
        List of TaskFileTreeNode representing the directory structure
    """
    nodes = []

    try:
        for item in sorted(directory.iterdir()):
            # Skip __pycache__ and hidden files
            if item.name.startswith('.') or item.name == '__pycache__':
                continue

            # Determine backend from path
            backend = None
            try:
                relative_parts = item.relative_to(base_path).parts
                if len(relative_parts) > 0:
                    backend = relative_parts[0]  # qubex, fake, etc.
            except ValueError:
                pass

            # Apply backend filter
            if backend_filter and backend != backend_filter:
                continue

            if item.is_dir():
                children = build_task_file_tree(item, base_path, backend_filter)
                if children:  # Only include non-empty directories
                    nodes.append(TaskFileTreeNode(
                        name=item.name,
                        path=str(item.relative_to(base_path)),
                        type="directory",
                        backend=backend,
                        children=children,
                    ))
            elif item.suffix == '.py':
                nodes.append(TaskFileTreeNode(
                    name=item.name,
                    path=str(item.relative_to(base_path)),
                    type="file",
                    backend=backend,
                ))
    except PermissionError:
        pass

    return nodes
```

#### Configuration Loader

**File Path**: `src/qdash/api/lib/task_editor_config.py`

```python
"""Task Editor configuration loader."""

from functools import lru_cache
from pathlib import Path
import yaml
from pydantic import BaseModel


class TaskEditorConfig(BaseModel):
    """Task Editor configuration."""

    enabled: bool = True
    read_only: bool = False
    base_path: str = "src/qdash/workflow/tasks"


@lru_cache(maxsize=1)
def load_task_editor_config() -> TaskEditorConfig:
    """Load task editor config from YAML or defaults.

    Returns:
        TaskEditorConfig with settings

    Raises:
        ValueError: If config file is invalid
    """
    # Try multiple possible locations
    possible_paths = [
        Path("/app/config/qdash.yaml"),  # Docker
        Path(__file__).parent.parent.parent.parent.parent / "config" / "qdash.yaml",  # Local
    ]

    config_path = None
    for path in possible_paths:
        if path.exists():
            config_path = path
            break

    if config_path:
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)
                return TaskEditorConfig(**data.get("task_editor", {}))
        except Exception as e:
            raise ValueError(f"Invalid task editor configuration: {e}") from e

    # Fallback to defaults
    return TaskEditorConfig()
```

### Frontend Implementation

#### Update Tasks Page

**File Path**: `ui/src/app/tasks/page.tsx`

```typescript
import { BsCode } from "react-icons/bs";
import { useRouter } from "next/navigation";

const TaskCard = ({ task }: { task: TaskResponse }) => {
  const router = useRouter();

  const openTaskEditor = () => {
    // Navigate to task editor with task context
    router.push(`/tasks/editor?task=${task.name}&backend=${task.backend}`);
  };

  return (
    <div className="card bg-base-100 shadow-lg hover:shadow-xl transition-all duration-300 group h-full">
      <div className="card-body flex flex-col p-4">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2 items-start">
            <h3 className="card-title text-lg group-hover:text-primary transition-colors break-all flex-1 min-w-0">
              {task.name}
            </h3>
            <div className="badge badge-primary badge-outline shrink-0">
              {task.task_type}
            </div>
          </div>
          {task.description && (
            <p className="text-base-content/70 mt-2 line-clamp-3">
              {task.description}
            </p>
          )}
        </div>

        {/* Action Buttons */}
        <div className="card-actions justify-end mt-4">
          <button
            className="btn btn-sm btn-outline gap-1"
            onClick={openTaskEditor}
          >
            <BsCode className="text-base" />
            View Code
          </button>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => setSelectedTask(task)}
          >
            Details
          </button>
        </div>
      </div>
    </div>
  );
};
```

#### Task Editor Page (New)

**File Path**: `ui/src/app/tasks/editor/page.tsx`

```typescript
"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "react-toastify";

import { getTaskFileTree, getTaskFileContent, saveTaskFileContent } from "@/client/task/task";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export default function TaskEditorPage() {
  const searchParams = useSearchParams();
  const taskName = searchParams.get("task");
  const backend = searchParams.get("backend");

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [isEditorLocked, setIsEditorLocked] = useState(true);

  // Fetch file tree
  const { data: fileTreeData } = useQuery({
    queryKey: ["taskFileTree", backend],
    queryFn: () => getTaskFileTree({ backend }).then(res => res.data),
  });

  // Fetch file content
  const { data: fileContentData } = useQuery({
    queryKey: ["taskFileContent", selectedFile],
    queryFn: () => getTaskFileContent({ path: selectedFile! }).then(res => res.data),
    enabled: !!selectedFile,
  });

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: (content: string) =>
      saveTaskFileContent({ path: selectedFile!, content }).then(res => res.data),
    onSuccess: () => {
      toast.success("File saved successfully!");
      setHasUnsavedChanges(false);
    },
    onError: (error: any) => {
      toast.error(`Failed to save: ${error.message}`);
    },
  });

  // Update content when file is loaded
  useEffect(() => {
    if (fileContentData?.content) {
      setFileContent(fileContentData.content);
      setHasUnsavedChanges(false);
      setIsEditorLocked(fileContentData.read_only ?? true);
    }
  }, [fileContentData]);

  const handleSave = () => {
    if (!selectedFile || !hasUnsavedChanges) return;
    saveMutation.mutate(fileContent);
  };

  // Rest of the implementation similar to Files Editor...
  // - File tree rendering
  // - Monaco Editor setup
  // - Lock/unlock mechanism
  // - Keyboard shortcuts (Ctrl+S)

  return (
    <div className="h-screen flex flex-col bg-[#1e1e1e]">
      {/* Header with breadcrumb, lock button, save button */}
      {/* Sidebar with file tree */}
      {/* Main editor area with Monaco Editor */}
      {/* Footer with cursor position, language info */}
    </div>
  );
}
```

#### API Client Functions

**File Path**: `ui/src/client/task/task.ts`

```typescript
import { apiClient } from "../apiClient";

export interface TaskFileTreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  backend?: string;
  category?: string;
  children?: TaskFileTreeNode[];
}

export const getTaskFileTree = async (params?: { backend?: string }) => {
  return apiClient.get<TaskFileTreeNode[]>("/tasks/files/tree", { params });
};

export const getTaskFileContent = async (params: { path: string }) => {
  return apiClient.get<{
    path: string;
    content: string;
    language: string;
    read_only: boolean;
  }>("/tasks/files/content", { params });
};

export const saveTaskFileContent = async (data: {
  path: string;
  content: string;
}) => {
  return apiClient.post<{ message: string; path: string }>(
    "/tasks/files/save",
    data,
  );
};
```

## Implementation Plan

### Phase 1: Backend Foundation

1. ✅ Create `config/qdash.yaml` configuration file
2. ✅ Add `TASK_BASE_PATH` to `.env.example`
3. ✅ Implement `task_editor_config.py` loader
4. ✅ Add `/tasks/files/tree` endpoint
5. ✅ Add `/tasks/files/content` endpoint
6. ✅ Add `/tasks/files/save` endpoint with read-only check
7. ✅ Implement `validate_task_file_path()` security function

### Phase 2: Frontend Integration

1. ✅ Create API client functions (`getTaskFileTree`, etc.)
2. ✅ Add "View Code" button to TaskCard component
3. ✅ Create `/tasks/editor` page (reuse Files Editor components)
4. ✅ Implement file tree navigation
5. ✅ Integrate Monaco Editor with Python syntax highlighting
6. ✅ Add lock/unlock mechanism
7. ✅ Add save functionality with syntax validation

### Phase 3: Testing & Documentation

1. ⬜ Test with different task files (qubex, fake backends)
2. ⬜ Test read-only mode enforcement
3. ⬜ Test path traversal security
4. ⬜ Update CLAUDE.md with Task Editor documentation
5. ⬜ Add user guide to docs/

### Phase 4: Optional Enhancements

1. ⬜ Git integration for task files (similar to Files Editor)
2. ⬜ Syntax highlighting for task-specific patterns (parameters, etc.)
3. ⬜ Auto-generate task documentation from code
4. ⬜ Diff view for task changes
5. ⬜ Task template generation

## Security Considerations

### Path Traversal Prevention

```python
def validate_task_file_path(relative_path: str) -> Path:
    """Prevent path traversal attacks like '../../../etc/passwd'"""

    # Block '..' in path
    if ".." in relative_path:
        raise HTTPException(status_code=400, detail="Path traversal detected")

    # Resolve to absolute path
    target_path = TASK_BASE_PATH / relative_path
    resolved_path = target_path.resolve()

    # Ensure resolved path is within TASK_BASE_PATH
    if not str(resolved_path).startswith(str(TASK_BASE_PATH.resolve())):
        raise HTTPException(status_code=400, detail="Path outside task directory")

    return resolved_path
```

### Python Syntax Validation

```python
# Validate before saving
try:
    compile(request.content, file_path.name, 'exec')
except SyntaxError as e:
    raise HTTPException(status_code=400, detail=f"Python syntax error: {e}")
```

### Read-Only Mode Enforcement

```python
config = load_task_editor_config()

if config.read_only:
    raise HTTPException(
        status_code=403,
        detail="Task editing is disabled (read_only mode)"
    )
```

### Authentication

All endpoints require `current_user` authentication via `Depends(get_current_active_user)`.

## Configuration Reference

### Environment Variables (`.env`)

```bash
# Task Editor paths
TASK_BASE_PATH="./src/qdash/workflow/tasks"
```

### Application Configuration (`config/qdash.yaml`)

```yaml
task_editor:
  enabled: true
  read_only: false # Set to true in production to prevent edits

  backends:
    qubex:
      categories:
        - one_qubit_coarse
        - one_qubit_fine
        - two_qubit
        - measurement
        - benchmark
        - system
    fake:
      categories: []
```

## References

- **Existing Files Editor**: `ui/src/app/files/page.tsx`
- **Task Base Class**: `src/qdash/workflow/tasks/base.py`
- **Task API Router**: `src/qdash/api/routers/task.py`
- **Metrics Config Loader**: `src/qdash/api/lib/metrics_config.py` (similar pattern)

## Change Log

- **2025-11-22**: Initial design document created
- **2025-11-22**: Configuration management strategy defined
- **2025-11-22**: Implementation plan outlined

## Future Considerations

1. **Task Template Generation**
   - Generate new task files from templates
   - Wizard-based task creation

2. **Code Intelligence**
   - Auto-completion for BaseTask methods
   - Type hints and inline documentation
   - Parameter validation hints

3. **Integration with Python Flow Editor**
   - Link task implementations to flow definitions
   - Visualize task dependencies

4. **Advanced Git Features**
   - Branch switching
   - Merge conflict resolution
   - Pull request creation from UI

---

**Document Status**: Draft
**Last Updated**: 2025-11-22
**Author**: System Design Team
**Reviewers**: TBD
