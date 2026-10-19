# API Contracts

Conventions for what a QDash API endpoint accepts and returns: query parameters, response models, errors and the OpenAPI text that describes them. Path, method and naming conventions are on [API Design](./design.md).

## Query Parameters

### Naming

Use **snake_case** for query parameters (FastAPI convention).

```python
# Good
@router.get("/executions")
def list_executions(
    chip_id: str = Query(..., description="Chip ID to filter"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
):
    pass

# Bad - camelCase query params
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
# Good
chip_id: str = Query(..., description="Chip ID to filter")
status: str = Query(None, description="Filter by status")
start_at: str = Query(None, description="Start time in ISO format")

# Bad
id: str = Query(...)          # Too generic
filter: str = Query(...)      # Too generic
```

## Response Model Design

### Wrap Collections in Response Objects

Always wrap collection responses in a response object with a descriptive field name.

```python
# Good - Wrapped response
class ListChipsResponse(BaseModel):
    chips: list[ChipResponse]

@router.get("/chips", response_model=ListChipsResponse)
def list_chips() -> ListChipsResponse:
    return ListChipsResponse(chips=[...])

# Bad - Raw list (makes future extension impossible)
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

# Good - Descriptive error
raise HTTPException(
    status_code=404,
    detail=f"Chip '{chip_id}' not found for user '{username}'"
)

# Bad - Generic error
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

## Documentation

### Endpoint summary

Use **imperative mood** (verb first) for endpoint summaries:

```python
# Good
summary="List all chips"
summary="Get a specific chip"
summary="Create a new chip"
summary="Delete a chip"

# Bad
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
