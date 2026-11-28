# API Code Structure

The API adapts HTTP requests to project-scoped services and repositories.

## Follow the Request Path

Authentication and project dependencies validate a request before its router calls a service.
The service applies domain rules and uses repositories for persistence.
`src/qdash/api/app/factory.py` assembles the application. Its `/api` root path is proxy metadata;
router declarations and `TestClient` requests use paths such as `/chips`.

## Put Code in the Owning Layer

Paths below are relative to `src/qdash/api/` unless shown otherwise.

| Location | Owns |
| --- | --- |
| `app/` | Application construction and router registration |
| `routers/` | HTTP input, dependencies, and responses |
| `schemas/` | Request and response models |
| `services/` | Domain rules and integration orchestration |
| `dependencies/` | Service and repository providers |
| `lib/auth.py`, `lib/project.py` | Identity and project permissions |
| `middleware/` | Request-wide behavior |
| `db/session.py` | Database connection lifecycle |
| `metric_runtime/` | Isolated metric execution and project-scoped data broker |
| `src/qdash/repository/` | Persistence and queries |

Keep routes thin. Match domain filenames across layers; split large services into packages
without changing their public contract.

## Wire Dependencies Through Providers

Inject providers with `Depends`; do not construct services in routes. Inject collaborators into
service constructors so tests can replace external systems.
`@cached_dependency_provider` caches long-lived providers. Tests that change their configuration
must call `clear_dependency_caches()`; HTTP tests must restore `app.dependency_overrides`.

## Register a Router Once

Add each router to `app/router_registry.py` with its tag, prefix, and authentication policy.
If a domain has public and protected routes, register separate router objects.

## Trace an Existing Endpoint

For a first change, follow `GET /chips`: `routers/chip.py` calls the provider in
`dependencies/__init__.py`, then `services/chip/service.py`; its response is declared in
`schemas/chip.py`. `tests/qdash/api/routers/test_chip.py` shows the user, project, and membership
fixtures needed to test it. Start with a similar existing route rather than inventing new wiring.

## Add or Change an Endpoint

1. Define schemas and service behavior, with focused tests.
2. Add a provider if needed.
3. Add the route with project permissions, response model, and explicit operation ID.
4. Register a new router.
5. Test serialization, authorization, and errors; run `task generate` for contract changes.

Follow [API Design](./design.md), [API Contracts](./contracts.md), and
[API Testing](./testing.md). Tests mirror source under `tests/qdash/api/`.
