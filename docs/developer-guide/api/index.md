# API Development

The QDash API owns authentication, authorization, project-scoped persistence, integration with
Prefect, and the HTTP contract consumed by the UI and generated clients.

## Choose the Right Guide

| Goal | Read |
| --- | --- |
| Design a route, method, operation ID, or router tag | [API Design Guidelines](./design.md) |
| Define query parameters, response models, or errors | [API Contracts](./contracts.md) |
| Place routers, schemas, services, and dependencies | [API Code Structure](./structure.md) |
| Choose a backend test layer and run the right suite | [API Testing](./testing.md) |
| Build endpoint fixtures and test authentication or project boundaries | [API Endpoint Testing](./endpoint-testing.md) |
| Inspect the generated HTTP surface | [OpenAPI Reference](../../reference/openapi.md) |

Start with design and contracts for a public API change, then use code structure to place the
implementation. Schema or route changes require `task generate` so the OpenAPI document and
TypeScript clients stay aligned.

## Source and Tests

API code lives under `src/qdash/api/`. Shared domain and persistence code lives under
`src/qdash/common/`, `src/qdash/datamodel/`, `src/qdash/dbmodel/`, and the repository modules.
Focused API tests live under `tests/qdash/api/`.

Run `task test-api` for API behavior and `task generate` when the public contract changes.
