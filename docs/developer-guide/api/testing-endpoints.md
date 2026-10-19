# API Endpoint Testing

Fixtures, database setup, endpoint tests, mocking, and async tests for the FastAPI backend;
naming, structure, assertions, and coverage rules are in [API Testing Guidelines](./testing.md).

## Fixtures

### Root Fixtures (`conftest.py`)

Define common fixtures at the root level:

```python
# tests/conftest.py

import pytest
from dataclasses import dataclass

@dataclass
class TestSettings:
    """Test configuration settings."""
    mongo_test_dsn: str = os.getenv("MONGO_TEST_DSN", "mongodb://root:example@mongo:27017")
    mongo_test_db: str = os.getenv("MONGO_TEST_DB", "qdash_test")


@pytest.fixture(scope="session")
def test_settings() -> TestSettings:
    """Get test settings."""
    return TestSettings()


@pytest.fixture(scope="session")
def mongo_client(test_settings: TestSettings) -> Generator[MongoClient, None, None]:
    """Create MongoDB client for testing (session-scoped)."""
    client: MongoClient = MongoClient(test_settings.mongo_test_dsn)
    yield client
    client.close()


@pytest.fixture
def init_db(mongo_client: MongoClient, test_settings: TestSettings) -> Generator[Database, None, None]:
    """Initialize Bunnet with test database."""
    from qdash.api.db.session import set_test_client

    set_test_client(mongo_client, db_name=test_settings.mongo_test_db)
    db = mongo_client[test_settings.mongo_test_db]
    yield db

    # Clean up: drop all collections after each test
    for collection_name in db.list_collection_names():
        db.drop_collection(collection_name)


@pytest.fixture
def test_client(init_db):
    """FastAPI test client with test MongoDB."""
    from fastapi.testclient import TestClient
    from qdash.api.main import app

    return TestClient(app)
```

### Fixture Scopes

| Scope      | Use Case                          | Example                         |
| ---------- | --------------------------------- | ------------------------------- |
| `function` | Default; fresh fixture per test   | `test_client`, `init_db`        |
| `class`    | Shared within test class          | Class-specific setup            |
| `module`   | Shared within test file           | Module-specific setup           |
| `session`  | Shared across entire test session | `mongo_client`, `test_settings` |

### Fixture Naming

```python
# Good - Descriptive fixture names
@pytest.fixture
def test_client():
    """FastAPI test client."""
    pass

@pytest.fixture
def system_info():
    """Create test system info."""
    pass

@pytest.fixture
def sample_chip():
    """Create a sample chip for testing."""
    pass

# Bad - Vague names
@pytest.fixture
def data():
    pass

@pytest.fixture
def fixture1():
    pass
```

### Autouse Fixtures

Use `autouse=True` sparingly, for setup that must run for every test:

```python
@pytest.fixture(autouse=True)
def _init_db(mongodb_client: MongoClient) -> None:
    """Initialize database before each test."""
    init_bunnet(
        database=mongodb_client.test_db,
        document_models=[ChipDocument],
    )
    # Clear collection before each test
    try:
        ChipDocument.get_motor_collection().drop()
    except Exception:
        pass
```

---

## Database Testing

Tests connect to the MongoDB instance running in Docker Compose through the session-scoped
`mongo_client` fixture above; `MONGO_TEST_DSN` and `MONGO_TEST_DB` override the connection.

Always clean up test data. The `init_db` fixture drops every collection in the test database
after each test, so tests never see data left behind by another test.

---

## API Endpoint Testing

### Basic Endpoint Test

```python
class TestChipRouter:
    """Tests for chip-related API endpoints."""

    def test_list_chips_empty(self, test_client):
        """Test listing chips when no chips exist."""
        response = test_client.get(
            "/api/chip",
            headers={"X-Username": "test_user"},
        )
        assert response.status_code == 200
        assert response.json() == []
```

### Testing with Authentication

Always include required headers:

```python
def test_fetch_chip_success(self, test_client):
    """Test fetching a specific chip by ID."""
    # Arrange
    chip = ChipDocument(
        chip_id="test_chip_fetch",
        username="test_user",
        size=144,
        system_info=SystemInfoModel(),
    )
    chip.insert()

    # Act
    response = test_client.get(
        "/api/chip/test_chip_fetch",
        headers={"X-Username": "test_user"},  # Required auth header
    )

    # Assert
    assert response.status_code == 200
```

### Testing Error Responses

```python
def test_fetch_chip_not_found(self, test_client):
    """Test fetching a non-existent chip returns 404."""
    response = test_client.get(
        "/api/chip/nonexistent_chip",
        headers={"X-Username": "test_user"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_chip_invalid_size(self, test_client):
    """Test creating a chip with invalid size returns 400."""
    response = test_client.post(
        "/api/chip",
        headers={"X-Username": "test_user"},
        json={"chip_id": "invalid_chip", "size": 100},  # Invalid size
    )

    assert response.status_code == 400
```

### Testing Access Control

```python
def test_fetch_chip_wrong_user(self, test_client):
    """Test that fetching another user's chip returns 404."""
    # Arrange: Create a chip for user1
    chip = ChipDocument(
        chip_id="user1_chip",
        username="user1",
        size=64,
        system_info=SystemInfoModel(),
    )
    chip.insert()

    # Act: Try to fetch as user2
    response = test_client.get(
        "/api/chip/user1_chip",
        headers={"X-Username": "user2"},
    )

    # Assert: Should not find the chip (access control)
    assert response.status_code == 404
```

---

## Mocking and Patching

### Using monkeypatch

Use pytest's `monkeypatch` fixture for patching:

```python
def test_flow_session_attributes(self, monkeypatch):
    """Test that FlowSession initializes with correct attributes."""

    # Mock ExecutionManager to avoid DB dependencies
    class MockExecutionManager:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.calib_data_path = kwargs.get("calib_data_path", "")
            self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()

        def save(self):
            return self

        def start_execution(self):
            return self

    class MockSession:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            pass

    # Patch the imports
    monkeypatch.setattr(
        "qdash.workflow.helpers.flow_helpers.ExecutionManager",
        MockExecutionManager,
    )
    monkeypatch.setattr(
        "qdash.workflow.helpers.flow_helpers.create_backend",
        lambda **kwargs: MockSession(),
    )

    # Create session
    session = FlowSession(
        username="test_user",
        execution_id="20240101-001",
        chip_id="chip_1",
    )

    # Verify
    assert session.username == "test_user"
```

### Mock Class Pattern

Create reusable mock classes:

```python
class MockExecutionManager:
    """Mock ExecutionManager for testing."""

    def __init__(self, **kwargs):
        self.calib_data_path = kwargs.get("calib_data_path", "")
        self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()
        self.completed = False

    def save(self):
        return self

    def start_execution(self):
        return self

    def complete_execution(self):
        self.completed = True
        return self
```

---

## Async Testing

### Configure pytest-asyncio

```python
# In conftest.py
pytest_plugins = ("pytest_asyncio",)
pytest.mark.asyncio_default_fixture_loop_scope = "function"
```

### Async Test Functions

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    """Test an async operation."""
    result = await some_async_function()
    assert result is not None
```

### Async Fixtures

```python
@pytest.fixture
async def async_client():
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

---

## Example Test File

```python
"""Tests for chip router endpoints."""

import pytest
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument


class TestChipRouter:
    """Tests for chip-related API endpoints."""

    def test_list_chips_empty(self, test_client):
        """Test listing chips when no chips exist."""
        response = test_client.get(
            "/api/chip",
            headers={"X-Username": "test_user"},
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_chips_with_data(self, test_client):
        """Test listing chips when chips exist."""
        # Arrange
        chip = ChipDocument(
            chip_id="test_chip_001",
            username="test_user",
            size=64,
            qubits={},
            couplings={},
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act
        response = test_client.get(
            "/api/chip",
            headers={"X-Username": "test_user"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["chip_id"] == "test_chip_001"
        assert data[0]["size"] == 64

    def test_fetch_chip_not_found(self, test_client):
        """Test fetching a non-existent chip returns 404."""
        response = test_client.get(
            "/api/chip/nonexistent_chip",
            headers={"X-Username": "test_user"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_chip_success(self, test_client):
        """Test creating a new chip."""
        response = test_client.post(
            "/api/chip",
            headers={"X-Username": "test_user"},
            json={"chip_id": "new_chip", "size": 64},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "new_chip"
        assert data["size"] == 64
```
