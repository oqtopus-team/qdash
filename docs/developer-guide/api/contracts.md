# API Contracts

Routes, typed parameters, schemas, and OpenAPI together define the public API.

## Model Request and Response Bodies

Keep HTTP models in `src/qdash/api/schemas/`. Set `response_model` on JSON routes and return that
type. Preserve existing list and wrapper shapes; adding pagination metadata does not justify
silently replacing a raw list with an object.

## Type Path and Query Parameters

Use snake_case names and domain types such as dates and enums. Add `Query` constraints when a
value has bounds. Keep pagination names and defaults consistent within each endpoint family.
FastAPI schema validation returns 422; domain validation uses the appropriate status below.

## Preserve Project Boundaries

Use dependencies from `src/qdash/api/lib/project.py`:

| Dependency | Access |
| --- | --- |
| `get_project_context` | Read |
| `get_project_context_editor` | Editor or owner |
| `get_project_context_owner` | Owner |
| `get_project_context_from_path` and role variants | Same checks with a path project ID |

Project resolution prefers the path, then `X-Project-Id`, the user's default, then an owned
project. Pass the resolved ID to services and repositories; do not trust a body-supplied ID.
Return 404 for a resource outside the resolved project to avoid revealing its existence.

## Return Stable Errors

| Status | Meaning |
| --- | --- |
| 400 | Invalid domain rule or field combination |
| 401 | Missing or invalid credentials |
| 403 | Insufficient permission |
| 404 | Resource absent in this scope |
| 409 | Conflicting resource or reservation state |
| 422 | Request schema validation failed |
| 502 | Invalid upstream response |
| 503 | Required service unavailable |

Use the JSON `detail` field, without exposing credentials or internal exception details.
Declare public errors in route metadata and test their status and payload.

## Keep OpenAPI and Clients Synchronized

After changing a route, parameter, schema, status, or operation ID:

```bash
task generate
task test-api
task test-client-ts
```

Never edit generated OpenAPI, UI clients/schemas, or TypeScript client files manually.
Review their diff for breaking paths, required fields, enum values, statuses, and response shapes.
Application-wide OpenAPI changes belong in `src/qdash/api/app/factory.py` and
`tests/qdash/api/test_app_factory.py`.
