# API Design

Routes expose stable HTTP contracts and client method names.

## Design Resource Paths

Use plural, lowercase resource names and kebab-case segments: `/chips/{chip_id}/qubits`.
Keep nesting shallow. Use an action suffix for non-CRUD work, such as
`POST /flows/{name}/execute`. Declare static routes before matching dynamic routes.
Do not rename an existing path just to make it consistent.

## Match the Method to the Effect

| Method | Effect |
| --- | --- |
| GET | Read |
| POST | Create or start an action |
| PUT | Replace or upsert |
| PATCH | Partially update |
| DELETE | Remove |

Choose the success status explicitly: 201 for creation, 202 for asynchronous work, and 204
only for an empty response. Preserve existing endpoint contracts.

## Treat Operation IDs as Client API Names

Set a unique camelCase `operation_id`, such as `listChips`, `getChip`, or `executeFlow`.
Generated clients use it as the method name, so renaming it breaks callers.
Use the corresponding snake_case name for the Python handler.

## Register Tags and Authentication Centrally

Register routers in `src/qdash/api/app/router_registry.py`. Keep tags, prefixes, and default
authentication there, with one owner for each. Protected routers receive the active-user check;
project-scoped routes also need the appropriate project-role dependency.
A public router still needs route-level checks wherever authentication is required.

## Keep Route Metadata Useful

Set `response_model`, a short summary, and the explicit operation ID. Describe side effects or
ordering only when the schema cannot express them. Keep handlers thin and put business rules in
services; see [API Code Structure](./structure.md).

For models, errors, compatibility, and regeneration, follow [API Contracts](./contracts.md).
Verify changes with [API Testing](./testing.md).
