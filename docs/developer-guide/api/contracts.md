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

Represent optional list queries as optional arrays in OpenAPI. Generated clients then send
one query key per element. For a plain-text response, declare the media type and string
schema so generated methods return the body, as in the task knowledge Markdown route.

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

### Report Unexpected File Operation Failures

Workspace text-file reads and saves, and workflow source reads, writes, creation, and deletion,
report unexpected failures with a safe `detail` string, a stable operation `code`, and an opaque
`error_id`. The API logs the same ID with the underlying traceback. Expected 4xx responses keep
their existing payloads.

Raise `OperationFailedError` from `qdash.api.lib.errors` with a fixed public message and chain
the original exception with `from exc`. Do not include exception text or internal paths in the
message, or log the same failure again in the service. The handler registered in the app factory
owns diagnostic logging. This exception currently extends `HTTPException` so existing HTTP-error
pass-through handlers preserve it.

Declare `OperationErrorDetail` from `qdash.api.schemas.error` in the route's `responses` metadata.
Its `code` and `error_id` fields are optional because other failure paths on the same routes still
return only `detail`. Directory preparation, deployment, dispatch, Git operations, and post-save
hooks are outside this migration; clients must continue to accept responses without an error ID.
The UI's `getApiErrorMessage` appends the ID when present. See
[error investigation](../../user-guide/operations.md#investigate-an-error-id) for the operator procedure.

Test the HTTP response and matching traceback log together, including absence of internal
exception text in the response. Keep regression coverage for expected errors and successful calls.

## Keep OpenAPI and Clients Synchronized

After changing a route, parameter, schema, status, or operation ID:

```bash
task generate
task test-api
task test-client-ts
```

Run generation with `npx` and a running Docker engine for the two Fern SDK generators.
Regenerate OpenAPI, clients, and SDK bindings from their sources.
Review their diff for breaking paths, required fields, enum values, statuses, and response shapes.
Application-wide OpenAPI changes belong in `src/qdash/api/app/factory.py` and
`tests/qdash/api/test_app_factory.py`.
