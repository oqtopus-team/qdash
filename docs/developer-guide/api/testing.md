# API Testing

API tests protect three boundaries separately: HTTP behavior in router tests, business rules in
service tests, and dependency wiring in focused provider tests.

## Choose the Narrowest Test Layer

| Change | Primary test location | Exercise |
| --- | --- | --- |
| Route, request, response, authentication, or authorization | `tests/qdash/api/routers/` | FastAPI application through `test_client` |
| Service rule or integration adapter | `tests/qdash/api/services/` | Service class with repositories and external clients replaced as needed |
| Request or response schema | `tests/qdash/api/schemas/` | Pydantic validation and serialization |
| Shared API helper | `tests/qdash/api/lib/` | Helper directly |
| Dependency provider or application construction | `tests/qdash/api/test_dependencies.py` or `test_app_factory.py` | Provider identity, cache reset, or router registration |

Put a behavior at the lowest layer that proves it. Add a router test when the HTTP contract or a
FastAPI dependency is part of the behavior; a service test alone cannot prove status codes,
headers, or response serialization.

## Mirror the Source Layout

Test paths follow the source paths:

```text
src/qdash/api/                      tests/qdash/api/
├── lib/project.py                  ├── lib/test_project_permissions.py
├── routers/chip.py                 ├── routers/test_chip.py
├── schemas/task_result.py          ├── schemas/test_task_result.py
├── services/flow_service.py        ├── services/test_flow_service.py
└── dependencies.py                 └── test_dependencies.py
```

Name test files `test_<source_module>.py`. Name a test for the action and observable result, such
as `test_get_chip_wrong_project` or `test_execute_flow_releases_claim_when_prefect_fails`. Classes
can group scenarios for one router or service, but they are not required.

## Structure One Behavior per Test

Arrange only the records and collaborators needed for the scenario, perform one action, and assert
the externally visible result. Comments for Arrange, Act, and Assert are useful only when those
phases are not already apparent.

Prefer exact assertions for stable contracts:

```python
response = test_client.get("/chips", headers=auth_headers)

assert response.status_code == 200
assert response.json() == {"chips": [], "total": 0}
```

For failures, assert the status and the structured error field that callers rely on. Avoid testing
only a fragment of a message when the API defines a stable error payload.

## Keep Test Data Local

The root `tests/conftest.py` supplies an in-memory MongoDB through `init_db` and the FastAPI
`test_client`. Add a fixture beside the tests when it belongs to one module, and move it to a
higher `conftest.py` only after multiple modules share the same setup.

Create project, user, and membership records explicitly when authorization is under test. Do not
reuse production configuration or credentials. The endpoint-specific fixture patterns are in
[API Endpoint Testing](./endpoint-testing.md).

Use `monkeypatch`, `MagicMock`, or `AsyncMock` at the boundary where QDash calls an external
system. Assert the important request made to that collaborator as well as the service result.
Do not mock the function whose behavior the test is meant to prove.

## Test Async Code Directly

Mark direct calls to async services with `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_execute_single_task_rejects_conflicting_resources(monkeypatch):
    monkeypatch.setattr(flow_service, "generate_execution_id", lambda *args, **kwargs: "exec-1")
    lock_repository = MagicMock()
    lock_repository.try_lock.return_value = False
    service = FlowService(
        flow_repository=MagicMock(),
        execution_lock_repository=lock_repository,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_single_task_from_snapshot(
            task_name="CheckRabi",
            qid="Q00",
            chip_id="chip-1",
            source_execution_id=None,
            username="operator",
            project_id="project-1",
        )

    assert exc_info.value.status_code == 409
    lock_repository.try_lock.assert_called_once()
```

Router tests remain synchronous because FastAPI's `TestClient` runs the async application for the
test. Use an async HTTP client only when the behavior specifically depends on an async client
lifecycle.

## Run Focused Tests First

Run the changed module while iterating, then the API suite before handing off a cross-cutting API
change:

```bash
uv run pytest tests/qdash/api/routers/test_chip.py -v
task test-api
```

Run `task test` when a change also affects shared repositories, data models, workflow code, or the
Python client. When a route or schema changes the public contract, run `task generate` and verify
the generated clients as described in [API Contracts](./contracts.md).

Coverage identifies untested branches but does not replace scenario selection. Prioritize success,
validation failure, missing resources, project isolation, insufficient permissions, and external
dependency failure where each applies.
