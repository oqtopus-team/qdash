# API Design Guidelines

## URL Path Design

### Use Plural Nouns for Collections

Always use **plural nouns** for resource collections. This maintains consistency and clearly indicates that the endpoint can return multiple resources.

```python
# ✅ Good
GET  /chips              # List all chips
GET  /chips/{chip_id}    # Get a specific chip
POST /chips              # Create a new chip

# ❌ Bad
GET  /chip               # Inconsistent - singular for collection
GET  /chip/{chip_id}     # Inconsistent
```

### Use Lowercase with Hyphens

- Use **lowercase letters** exclusively
- Use **hyphens (`-`)** to separate words (kebab-case)
- Never use underscores, camelCase, or PascalCase in URLs

```python
# ✅ Good
/task-results
/execution-history
/flow-schedules

# ❌ Bad
/taskResults        # camelCase
/task_results       # underscores
/TaskResults        # PascalCase
```

### Resource Hierarchy and Nesting

Use nesting to show relationships, but limit to 2-3 levels maximum.

```python
# ✅ Good - Clear hierarchy
GET /chips/{chip_id}/muxes                    # Muxes belonging to a chip
GET /chips/{chip_id}/muxes/{mux_id}           # Specific mux
GET /task-results/qubits/{qid}/history        # Qubit task history

# ❌ Bad - Too deeply nested
GET /users/{user_id}/chips/{chip_id}/qubits/{qid}/tasks/{task_id}/results
```

### Singleton Resources

Use singular form only for singleton resources (resources that exist as a single instance).

```python
# ✅ Good - Singleton
GET  /settings                                # Application settings (only one)
GET  /executions/lock-status                  # Lock status (singleton)

# ✅ Good - Collection
GET  /chips                                   # Multiple chips
GET  /executions                              # Multiple executions
```

### Action Endpoints

For actions that don't fit standard CRUD operations, use verbs as sub-resources.

```python
# ✅ Good
POST /flows/{name}/execute                    # Execute a flow
POST /flows/{name}/schedule                   # Schedule a flow

# ❌ Bad
POST /execute-flow/{name}                     # Verb in wrong position
POST /flowExecute/{name}                      # camelCase, poor structure
```

---

## HTTP Methods

Use HTTP methods according to their semantic meaning:

| Method   | Purpose                 | Idempotent | Response                 |
| -------- | ----------------------- | ---------- | ------------------------ |
| `GET`    | Retrieve resource(s)    | Yes        | 200 OK                   |
| `POST`   | Create new resource     | No         | 201 Created              |
| `PUT`    | Replace entire resource | Yes        | 200 OK                   |
| `PATCH`  | Partial update          | No         | 200 OK                   |
| `DELETE` | Remove resource         | Yes        | 204 No Content or 200 OK |

### Guidelines

```python
# ✅ Good
@router.get("/chips")                         # List chips
@router.get("/chips/{chip_id}")               # Get single chip
@router.post("/chips")                        # Create chip
@router.put("/chips/{chip_id}")               # Replace chip entirely
@router.patch("/chips/{chip_id}")             # Update chip partially
@router.delete("/chips/{chip_id}")            # Delete chip

# ❌ Bad
@router.post("/chips/{chip_id}/delete")       # Don't use POST for delete
@router.get("/chips/create")                  # Don't use GET for create
```

---

## Operation ID Naming

### Use camelCase Format

All `operation_id` values must use **camelCase** format for consistency and SDK generation compatibility.

```python
# ✅ Good - camelCase
operation_id="listChips"
operation_id="getChip"
operation_id="createChip"
operation_id="updateChip"
operation_id="deleteChip"

# ❌ Bad - snake_case
operation_id="list_chips"
operation_id="get_chip"
```

### Verb + Noun Pattern

Follow the **verb + noun** pattern consistently:

| Action              | Verb             | Example                        |
| ------------------- | ---------------- | ------------------------------ |
| List collection     | `list`           | `listChips`, `listExecutions`  |
| Get single resource | `get`            | `getChip`, `getExecution`      |
| Create resource     | `create`         | `createChip`, `createFlow`     |
| Update resource     | `update`         | `updateChip`, `updateSchedule` |
| Delete resource     | `delete`         | `deleteChip`, `deleteFlow`     |
| Custom action       | descriptive verb | `executeFlow`, `scheduleFlow`  |

### Consistency Rules

1. **Use `list` for collections**: Not `fetch`, `getAll`, or `fetchAll`
2. **Use `get` for single resources**: Not `fetch`, `retrieve`, or `read`
3. **Include resource name**: Always include the noun

```python
# ✅ Good - Consistent verbs
operation_id="listChips"
operation_id="listExecutions"
operation_id="listTasks"
operation_id="listFlows"

operation_id="getChip"
operation_id="getExecution"
operation_id="getTask"
operation_id="getFlow"

# ❌ Bad - Inconsistent verbs
operation_id="fetchChips"      # Use 'list' instead
operation_id="getAll"          # Missing resource name
operation_id="retrieveChip"    # Use 'get' instead
```

### Nested Resources

For nested resources, include the parent context if it improves clarity:

```python
# ✅ Good
operation_id="listChipMuxes"                  # Muxes under a chip
operation_id="getChipMux"                     # Single mux under a chip
operation_id="listFlowSchedules"              # Schedules for a flow

# For deeply nested or context-heavy endpoints
operation_id="getQubitTaskHistory"            # Task history for qubit
operation_id="getCouplingTaskHistory"         # Task history for coupling
```

---

## Function Naming

### Alignment with Operation ID

**Function names must align with their `operation_id`**. The function name should be the **snake_case version** of the `operation_id`. This ensures:

1. **Predictability**: Developers can easily find functions by operation_id and vice versa
2. **Code generation compatibility**: Generated SDKs use operation_id as method names
3. **Consistency**: Reduces cognitive load when switching between API docs and code

```python
# ✅ Good - Function name matches operation_id (snake_case ↔ camelCase)
@router.get("/chips", operation_id="listChips")
def list_chips():                               # listChips → list_chips
    pass

@router.get("/chips/{chip_id}", operation_id="getChip")
def get_chip(chip_id: str):                     # getChip → get_chip
    pass

@router.post("/flows/{name}/execute", operation_id="executeFlow")
async def execute_flow(name: str):              # executeFlow → execute_flow
    pass

# ❌ Bad - Function name doesn't match operation_id
@router.get("/me", operation_id="getCurrentUser")
def read_users_me():                            # Should be get_current_user

@router.get("/settings", operation_id="getSettings")
def get_settings_endpoint():                    # Should be get_settings (no suffix)

@router.get("/task-results", operation_id="getLatestQubitTaskResults")
def fetch_latest_qubit_task_results():          # Should be get_latest_qubit_task_results
```

### Conversion Rules

| operation_id (camelCase) | Function name (snake_case) |
| ------------------------ | -------------------------- |
| `listChips`              | `list_chips`               |
| `getChip`                | `get_chip`                 |
| `createChip`             | `create_chip`              |
| `updateChip`             | `update_chip`              |
| `deleteChip`             | `delete_chip`              |
| `executeFlow`            | `execute_flow`             |
| `getQubitTaskHistory`    | `get_qubit_task_history`   |

### Verb Consistency

Use the same verb in both operation_id and function name:

| operation_id verb | Function name verb | Notes                    |
| ----------------- | ------------------ | ------------------------ |
| `list`            | `list_`            | For collections          |
| `get`             | `get_`             | For single resources     |
| `create`          | `create_`          | For creating resources   |
| `update`          | `update_`          | For modifying resources  |
| `delete`          | `delete_`          | For removing resources   |
| `execute`         | `execute_`         | For action endpoints     |
| `schedule`        | `schedule_`        | For scheduling endpoints |

**Avoid these inconsistencies:**

```python
# ❌ Bad - Verb mismatch
operation_id="getTaskResults"
def fetch_task_results():          # 'fetch' vs 'get' - use get_task_results

operation_id="listExecutions"
def read_executions():             # 'read' vs 'list' - use list_executions

# ❌ Bad - Unnecessary suffixes
operation_id="getSettings"
def get_settings_endpoint():       # '_endpoint' suffix - use get_settings

operation_id="listFlows"
def list_flows_handler():          # '_handler' suffix - use list_flows
```

### Private/Helper Functions

Helper functions that are not endpoints should use a leading underscore:

```python
# ✅ Good - Clear distinction between endpoints and helpers
@router.get("/muxes/{mux_id}", operation_id="getChipMux")
def get_chip_mux(mux_id: int) -> MuxDetailResponse:
    return _build_mux_detail(mux_id, tasks, task_results)

def _build_mux_detail(mux_id: int, tasks: list, task_results: dict) -> MuxDetailResponse:
    """Helper function - not an endpoint."""
    pass
```

---

## Response Model Design

### Wrap Collections in Response Objects

Always wrap collection responses in a response object with a descriptive field name.

```python
# ✅ Good - Wrapped response
class ListChipsResponse(BaseModel):
    chips: list[ChipResponse]

@router.get("/chips", response_model=ListChipsResponse)
def list_chips() -> ListChipsResponse:
    return ListChipsResponse(chips=[...])

# ❌ Bad - Raw list (makes future extension impossible)
@router.get("/chips", response_model=list[ChipResponse])
def list_chips() -> list[ChipResponse]:
    return [...]
```

### Benefits of Wrapped Responses

1. **Extensibility**: Easy to add metadata like pagination
2. **Consistency**: Same structure across all list endpoints
3. **Client friendliness**: Clear field names for deserialization

```python
# Future-proof: can add pagination without breaking clients
class ListChipsResponse(BaseModel):
    chips: list[ChipResponse]
    total: int | None = None
    page: int | None = None
    per_page: int | None = None
```

### Naming Conventions for Response Models

| Type                   | Pattern                      | Example                                  |
| ---------------------- | ---------------------------- | ---------------------------------------- |
| List response          | `List{Resource}sResponse`    | `ListChipsResponse`, `ListTasksResponse` |
| Single resource        | `{Resource}Response`         | `ChipResponse`, `TaskResponse`           |
| Detail response        | `{Resource}DetailResponse`   | `ExecutionDetailResponse`                |
| Create/Update response | `{Action}{Resource}Response` | `CreateChipResponse`                     |

---

## Query Parameters

### Naming

Use **snake_case** for query parameters (FastAPI convention).

```python
# ✅ Good
@router.get("/executions")
def list_executions(
    chip_id: str = Query(..., description="Chip ID to filter"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
):
    pass

# ❌ Bad - camelCase query params
@router.get("/executions")
def list_executions(
    chipId: str = Query(...),  # Should be chip_id
):
    pass
```

### Pagination

Use consistent pagination parameters across all list endpoints:

```python
skip: int = Query(0, ge=0, description="Number of items to skip")
limit: int = Query(20, ge=1, le=100, description="Number of items to return")
```

### Filtering

Use descriptive parameter names that match the field being filtered:

```python
# ✅ Good
chip_id: str = Query(..., description="Chip ID to filter")
status: str = Query(None, description="Filter by status")
start_at: str = Query(None, description="Start time in ISO format")

# ❌ Bad
id: str = Query(...)          # Too generic
filter: str = Query(...)      # Too generic
```

---

## Error Handling

### Use Appropriate HTTP Status Codes

| Status                    | Use Case                            |
| ------------------------- | ----------------------------------- |
| 400 Bad Request           | Invalid input, validation errors    |
| 401 Unauthorized          | Authentication required             |
| 403 Forbidden             | Authenticated but not authorized    |
| 404 Not Found             | Resource doesn't exist              |
| 409 Conflict              | Resource conflict (e.g., duplicate) |
| 500 Internal Server Error | Server-side errors                  |

### Error Response Format

Use consistent error response format:

```python
from fastapi import HTTPException

# ✅ Good - Descriptive error
raise HTTPException(
    status_code=404,
    detail=f"Chip '{chip_id}' not found for user '{username}'"
)

# ❌ Bad - Generic error
raise HTTPException(status_code=404, detail="Not found")
```

### Document Error Responses

```python
@router.get(
    "/chips/{chip_id}",
    responses={
        404: {"model": ErrorResponse, "description": "Chip not found"},
        403: {"model": ErrorResponse, "description": "Access denied"},
    },
)
def get_chip(chip_id: str) -> ChipResponse:
    pass
```

---

## Documentation

### Summary

Use **imperative mood** (verb first) for endpoint summaries:

```python
# ✅ Good
summary="List all chips"
summary="Get a specific chip"
summary="Create a new chip"
summary="Delete a chip"

# ❌ Bad
summary="Chips listing"           # Noun phrase
summary="Fetches all chips"       # Third person
summary="list all chip"           # Lowercase, singular
```

### Description

Provide detailed descriptions for complex endpoints:

```python
@router.get(
    "/task-results/qubits/latest",
    summary="Get latest qubit task results",
    description="""
    Fetch the most recent task results for all qubits in a chip.

    Results are filtered by the specified task name and include
    output parameters and execution metadata.
    """,
)
```

### Parameter Documentation

Always document parameters with descriptions:

```python
chip_id: Annotated[str, Query(description="Unique identifier of the chip")]
task: Annotated[str, Query(description="Name of the task to filter by")]
```

---

## Resource Naming

### Domain Resources

Resource names should be clear, domain-specific nouns that represent the entities in the system.

### Nested Resource Patterns

When resources have parent-child relationships, use nesting to express hierarchy:

```python
# ✅ Good - Clear hierarchy
GET /resources/{id}/sub-resources                    # All sub-resources for a resource
GET /resources/{id}/sub-resources/{sub_id}           # Specific sub-resource
GET /results/items/{item_id}/history                 # Item history

# ❌ Bad - Too deeply nested
GET /users/{user_id}/resources/{id}/items/{item_id}/results/{result_id}
```

### Resource Naming Rules

1. **Use domain terminology**: Use terms familiar to quantum computing (qubits, couplings, fidelity)
2. **Be specific**: `task-results` not `results`, `flow-schedules` not `schedules`
3. **Avoid abbreviations**: `executions` not `execs`, `configurations` not `configs`
4. **Use hyphens for multi-word**: `task-results`, `device-topology`, `lock-status`

---

## Router Tags

### Tag Naming Convention

Router tags are used for OpenAPI documentation grouping and should use **lowercase singular** or **kebab-case** format.

```python
# ✅ Good - Consistent tag naming
app.include_router(resource.router, tags=["resource"])
app.include_router(sub_resource.router, tags=["sub-resource"])

# ❌ Bad - Inconsistent
app.include_router(resource.router, tags=["resources"])          # Plural
app.include_router(resource.router, tags=["Resource"])           # PascalCase
app.include_router(sub_resource.router, tags=["sub_resource"])   # Underscore
```

### Tag Organization in OpenAPI

Tags appear in the order they are registered. Group related tags together:

```python
# Core resources
app.include_router(resource.router, tags=["resource"])
app.include_router(item.router, tags=["item"])

# Operations
app.include_router(execution.router, tags=["execution"])
app.include_router(workflow.router, tags=["workflow"])

# Configuration
app.include_router(settings.router, tags=["settings"])
app.include_router(config.router, tags=["config"])
```

---

## File Naming

### Router Files

Router files should use **snake_case** matching the resource name:

```
src/project/api/routers/
├── resource.py           # Resource endpoints
├── sub_resource.py       # Multi-word resource endpoints
├── auth.py               # Authentication endpoints
└── settings.py           # Settings endpoints
```

### Schema Files

Schema files should match their corresponding router:

```
src/project/api/schemas/
├── resource.py           # ResourceResponse, ListResourcesResponse, etc.
├── sub_resource.py       # SubResourceResponse, etc.
├── auth.py               # User, TokenResponse, etc.
└── error.py              # ErrorResponse, Detail
```

### Naming Rules

| Type            | Convention      | Example                |
| --------------- | --------------- | ---------------------- |
| Router file     | `snake_case.py` | `task_result.py`       |
| Schema file     | `snake_case.py` | `task_result.py`       |
| Response model  | `PascalCase`    | `ListChipsResponse`    |
| Request model   | `PascalCase`    | `CreateChipRequest`    |
| Router variable | `router`        | `router = APIRouter()` |

### Import Conventions

```python
# In main.py - import router modules
from project.api.routers import (
    auth,
    resource,
    sub_resource,
    settings,
)

# In router files - import schemas
from project.api.schemas.resource import (
    ResourceResponse,
    CreateResourceRequest,
    ListResourcesResponse,
)
```

---

## Migration Strategy

When adding new endpoints or modifying existing ones:

1. **Follow conventions from the start**: Use this guide for all new development
2. **Update clients immediately**: Regenerate API clients after changes (`bun run generate-qdash`)
3. **Avoid breaking changes**: If breaking changes are necessary, use versioning or deprecation

### Deprecation Pattern

```python
# Step 1: Add new endpoint, deprecate old
@router.get("/chip", deprecated=True)  # Old - mark as deprecated
def list_chips_deprecated():
    return list_chips()

@router.get("/chips", response_model=ListChipsResponse)  # New
def list_chips():
    pass
```

### Versioning Pattern

```python
# For significant breaking changes, consider API versioning
@router.get("/v2/chips", response_model=ListChipsResponse)
def list_chips_v2():
    pass
```

