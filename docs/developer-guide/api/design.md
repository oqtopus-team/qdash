# API Design

A QDash route exposes a stable resource-oriented HTTP contract; its path, method, and
`operation_id` must remain predictable for people and generated clients.

## Design Resource Paths

Use lowercase plural nouns for collections and kebab-case for multiword segments:

```text
GET  /chips
GET  /chips/{chip_id}
GET  /task-results
GET  /device-topology
```

Nest a resource when the parent identifies its scope. Keep the hierarchy shallow enough that the
resource is still recognizable:

```text
GET /chips/{chip_id}/qubits
GET /chips/{chip_id}/qubits/{qid}
GET /flows/{name}/schedules
```

Use a verb after the resource for an operation that is not CRUD:

```text
POST /flows/{name}/execute
POST /executions/{flow_run_id}/cancel
POST /calibration-pipelines/validate
```

Static routes must be declared before a dynamic route that could consume the same segment.
`src/qdash/api/routers/flow.py` declares `/flows/templates` and `/flows/schedules` before
`/flows/{name}` for this reason.

Existing paths are public contracts even when they predate these conventions. Do not rename one
only for consistency; use the compatibility process in [API Contracts](./contracts.md).

## Match the Method to the Effect

| Method | Use |
| --- | --- |
| `GET` | Read without changing server state |
| `POST` | Create a resource or start an action |
| `PUT` | Replace or upsert the complete representation at a known path |
| `PATCH` | Change part of an existing resource |
| `DELETE` | Remove a resource or relationship |

Choose the success status as part of the contract. FastAPI defaults to `200`; specify `201` for a
created resource, `202` when work continues asynchronously, and `204` only when the response has no
body. Match an existing endpoint family when extending it, because changing an established success
status can break callers.

## Treat Operation IDs as Client API Names

Every new route must set a unique camelCase `operation_id`. The TypeScript generator uses it as the
exported method name, so changing `listChips` also renames
`client.api.listChips()`.

Use an action and domain noun:

| Purpose | Pattern | Example |
| --- | --- | --- |
| Collection read | `list<Resource>` | `listChips` |
| Single read | `get<Resource>` | `getChip` |
| Creation | `create<Resource>` | `createCryostat` |
| Mutation | `update<Resource>`, `set<Resource>` | `updateFlowSchedule` |
| Removal | `delete<Resource>` | `deleteChip` |
| Domain action | Specific verb | `executeFlow`, `cancelExecution` |

Name the Python handler with the snake_case form when that remains clear:
`operation_id="getChipDeletionImpact"` pairs with `get_chip_deletion_impact()`. The ID is the
public contract; the handler name is an internal navigation aid.

`src/qdash/api/app/factory.py` provides `custom_generate_unique_id()` as a fallback, but new routes
must not rely on the tag-and-function-name fallback. Explicit IDs remain stable if registration or
internal function names change.

## Register Tags and Authentication Centrally

`src/qdash/api/app/router_registry.py` is the inventory of mounted routers. Each
`RouterRegistration` owns the router's OpenAPI tag, optional path prefix, and default authentication
policy.

Use a stable kebab-case domain tag such as `agent-session` or `device-topology`. Add the tag in the
registry rather than both the `APIRouter` and `include_router()`; duplicate registration produces
duplicate OpenAPI tags. Preserve an existing tag spelling because OpenAPI navigation and fallback
operation IDs expose it.

Protected routers receive `get_current_active_user` at registration. Routes still add
`get_project_context`, `get_project_context_editor`, or an owner dependency when they need a
project and role. A router marked public skips only the registry-level check; each public route
remains responsible for any authentication it requires.

## Keep Route Metadata Useful

Write a short imperative summary such as “List all chips” or “Execute a flow.” Use a longer
description only when a caller needs behavior that the schemas cannot express, such as ordering,
fallbacks, or side effects.

A typical route makes all client-facing decisions visible in its decorator and signature:

```python
@router.get(
    "/chips",
    response_model=ListChipsResponse,
    summary="List all chips",
    operation_id="listChips",
)
def list_chips(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> ListChipsResponse:
    chips = chip_service.list_chips_summary(ctx.project_id)
    return ListChipsResponse(chips=chips, total=len(chips))
```

The request and response rules are in [API Contracts](./contracts.md). Router placement,
dependency providers, and the request path through the application are in
[API Code Structure](./structure.md).
