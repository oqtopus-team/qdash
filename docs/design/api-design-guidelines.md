# API Design Guidelines for QDash

This document defines the API design conventions and standards for the QDash project. All contributors should follow these guidelines when creating new endpoints or refactoring existing ones.

## Table of Contents

1. [URL Path Design](#url-path-design)
2. [HTTP Methods](#http-methods)
3. [Operation ID Naming](#operation-id-naming)
4. [Response Model Design](#response-model-design)
5. [Query Parameters](#query-parameters)
6. [Error Handling](#error-handling)
7. [Documentation](#documentation)
8. [Current State and Migration](#current-state-and-migration)

---

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

| Method | Purpose | Idempotent | Response |
|--------|---------|------------|----------|
| `GET` | Retrieve resource(s) | Yes | 200 OK |
| `POST` | Create new resource | No | 201 Created |
| `PUT` | Replace entire resource | Yes | 200 OK |
| `PATCH` | Partial update | No | 200 OK |
| `DELETE` | Remove resource | Yes | 204 No Content or 200 OK |

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

| Action | Verb | Example |
|--------|------|---------|
| List collection | `list` | `listChips`, `listExecutions` |
| Get single resource | `get` | `getChip`, `getExecution` |
| Create resource | `create` | `createChip`, `createFlow` |
| Update resource | `update` | `updateChip`, `updateSchedule` |
| Delete resource | `delete` | `deleteChip`, `deleteFlow` |
| Custom action | descriptive verb | `executeFlow`, `scheduleFlow` |

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

| Type | Pattern | Example |
|------|---------|---------|
| List response | `List{Resource}sResponse` | `ListChipsResponse`, `ListTasksResponse` |
| Single resource | `{Resource}Response` | `ChipResponse`, `TaskResponse` |
| Detail response | `{Resource}DetailResponse` | `ExecutionDetailResponse` |
| Create/Update response | `{Action}{Resource}Response` | `CreateChipResponse` |

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

| Status | Use Case |
|--------|----------|
| 400 Bad Request | Invalid input, validation errors |
| 401 Unauthorized | Authentication required |
| 403 Forbidden | Authenticated but not authorized |
| 404 Not Found | Resource doesn't exist |
| 409 Conflict | Resource conflict (e.g., duplicate) |
| 500 Internal Server Error | Server-side errors |

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

## Current State and Migration

### Current Inconsistencies

The existing API has the following inconsistencies that should be addressed during refactoring:

#### 1. Endpoint Paths (Singular vs Plural)

| Current | Should Be |
|---------|-----------|
| `/chip` | `/chips` |
| `/tag` | `/tags` |
| `/backend` | `/backends` |
| `/task/{task_id}` | `/tasks/{task_id}` |
| `/flow` | `/flows` |

#### 2. Operation IDs (snake_case → camelCase)

| Current | Should Be |
|---------|-----------|
| `fetch_all_tasks` | `listTasks` |
| `get_task_result_by_task_id` | `getTaskResult` |
| `save_flow` | `createFlow` or `saveFlow` |
| `list_flows` | `listFlows` |
| `fetch_config` | `getSettings` |

#### 3. Response Models (Raw List → Wrapped)

| Current | Should Be |
|---------|-----------|
| `list[ChipResponse]` | `ListChipsResponse` |
| `list[BackendResponseModel]` | `ListBackendsResponse` |

### Migration Strategy

When refactoring endpoints:

1. **Create new endpoint** with correct conventions
2. **Deprecate old endpoint** (add deprecation notice)
3. **Update clients** to use new endpoint
4. **Remove old endpoint** after transition period

```python
# Step 1 & 2: Add new endpoint, deprecate old
@router.get("/chip", deprecated=True)  # Old
def list_chips_deprecated():
    return list_chips()

@router.get("/chips", response_model=ListChipsResponse)  # New
def list_chips():
    pass
```

---

## Quick Reference

### URL Path Checklist

- [ ] Uses plural nouns for collections
- [ ] Uses lowercase letters only
- [ ] Uses hyphens for word separation
- [ ] Nesting limited to 2-3 levels
- [ ] Actions use POST with verb sub-resource

### Operation ID Checklist

- [ ] Uses camelCase
- [ ] Follows verb + noun pattern
- [ ] Uses consistent verbs (list, get, create, update, delete)
- [ ] Includes resource name

### Response Model Checklist

- [ ] Collections wrapped in response object
- [ ] Follows naming convention (List{Resource}sResponse)
- [ ] Single resources use {Resource}Response

### Documentation Checklist

- [ ] Summary uses imperative mood
- [ ] All parameters have descriptions
- [ ] Error responses documented

---

## References

- [Microsoft REST API Guidelines](https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design)
- [OpenAPI Best Practices](https://learn.openapis.org/best-practices.html)
- [REST API URI Naming Conventions](https://restfulapi.net/resource-naming/)
- [OpenAPI Operation ID Best Practices](https://www.speakeasy.com/blog/how-to-set-operationid)
