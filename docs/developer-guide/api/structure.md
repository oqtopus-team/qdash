# API Code Structure

How routers, schemas, services and dependencies are laid out under `src/qdash/api/`, and how an endpoint is evolved without breaking clients. The conventions for the endpoints themselves are on [API Design](./design.md) and [API Contracts](./contracts.md).

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

## Service Layer

Business logic lives in service classes under `src/qdash/api/services/`. Routers handle HTTP concerns only (request parsing, response formatting, status codes) and delegate to services.

### File Layout

```
src/qdash/api/
├── routers/           # HTTP layer: request/response, DI, status codes
│   ├── copilot.py
│   ├── forum.py
│   └── auth.py
├── services/          # Business logic: data loading, validation, orchestration
│   ├── copilot_data_service.py
│   └── auth_service.py
├── lib/               # Shared utilities: SSE formatting, auth helpers, config
│   ├── sse.py
│   ├── file_utils.py
│   └── copilot_analysis.py
├── schemas/           # Pydantic request/response models
└── dependencies.py    # DI wiring (@lru_cache singletons)
```

### Dependency Injection

Services are instantiated as singletons via `@lru_cache` functions in `dependencies.py` and injected into routers with `Depends()`.

```python
# dependencies.py
@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService(
        user_repository=get_user_repository(),
        project_service=get_project_service(),
    )

# routers/auth.py
@router.post("/register")
def register_user(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserWithToken:
    user, _ = auth_service.register_user(user_data, admin)
    auth_service.onboard_user(user)
    return UserWithToken(...)
```

### Guidelines

- **One service per domain** -- `ForumService` handles the forum, `AuthService` handles auth.
- **Routers stay thin** -- No DB queries, no business rules, no data transformation in routers.
- **Services are framework-agnostic** -- Services raise `HTTPException` for now but don't depend on `Request`/`Response`.
- **Static methods for pure logic** -- Use `@staticmethod` for functions that don't need instance state (e.g., `ForumService.strip_mention()`).
- **Compose via constructor injection** -- If service A needs service B, inject B through `__init__`.

## Migration Strategy

When adding new endpoints or modifying existing ones:

1. **Follow conventions from the start**: Apply [API Design](./design.md) and [API Contracts](./contracts.md) to all new development
2. **Update clients immediately**: Regenerate API clients after changes (`task generate`)
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
