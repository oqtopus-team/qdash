# API Testing

Test each behavior at the lowest layer that proves it.

## Choose the Narrowest Test Layer

| Behavior | Tests under `tests/qdash/api/` |
| --- | --- |
| HTTP contract and permissions | `routers/` |
| Domain rules and integrations | `services/` |
| Validation and serialization | `schemas/` |
| Helpers | `lib/` |
| Application and provider wiring | `test_app_factory.py`, `test_dependencies.py` |

## Test an Endpoint

`tests/conftest.py` provides a fresh in-memory database through `init_db` and the FastAPI
`test_client`. Fixtures inserting Bunnet documents must depend on one of these fixtures.
Use route paths without `/api`.

Create a user, project, and membership, then send matching bearer and `X-Project-Id` headers.
Use the minimum role the route requires. Cover missing credentials, disabled users,
insufficient permissions, and resources in another project.

Assert the response status and stable payload. For writes, also inspect stored records.
For lists, include another project's record and prove it is excluded. Send JSON when testing
request validation so the test exercises the HTTP boundary.

## Replace External Boundaries

Replace network, filesystem, and orchestration calls where QDash imports them. Do not mock the
behavior being tested. Root fixtures stub Prefect; no server is needed for ordinary API tests.
Use `tmp_path` for files and restore dependency overrides and mutable globals after each test.
Failure tests must prove cleanup, including releasing reservations after dispatch failure.

## Test Async Services Directly

Use `@pytest.mark.asyncio` for direct async calls. Router tests can remain synchronous with
`TestClient`. Wait for observable completion rather than sleeping.

## Run Focused Tests First

```bash
uv run pytest tests/qdash/api/routers/test_chip.py -v
task test-api
```

Run `task test` when shared models, repositories, or workflow code also change. For public
contract changes, regenerate and test clients as described in [API Contracts](./contracts.md).
