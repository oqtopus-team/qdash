# API Testing Guidelines

How backend tests are laid out, named, structured, and measured; fixtures, database setup,
endpoint tests, mocking, and async tests are in [API Endpoint Testing](./endpoint-testing.md).

## Test Directory Structure

### Mirror the Source Structure

Tests should mirror the structure of the source code they test:

```
tests/
├── conftest.py                      # Root fixtures (database, test client)
├── fixtures/                        # Shared fixtures
│   ├── __init__.py
│   ├── database.py                  # Database fixtures
│   └── api.py                       # API fixtures
├── data/                            # Test data
│   ├── __init__.py
│   └── sample_data.py               # Sample data for tests
├── utils/                           # Test utilities
│   └── helpers.py                   # Helper functions
└── qdash/                           # Tests (mirrors src/qdash/)
    ├── api/
    │   ├── __init__.py
    │   └── routers/
    │       ├── __init__.py
    │       ├── test_chip.py         # Tests for chip router
    │       └── test_execution.py    # Tests for execution router
    ├── dbmodel/
    │   ├── conftest.py              # DB model specific fixtures
    │   ├── __init__.py
    │   └── test_chip.py             # Tests for ChipDocument
    └── workflow/
        ├── __init__.py
        ├── helpers/
        │   └── test_flow_helpers.py # Tests for flow helpers
        └── engine/
            └── calibration/
                └── test_cr_scheduler.py
```

### Guidelines

- **Mirror source structure**: `tests/qdash/api/routers/` corresponds to `src/qdash/api/routers/`
- **Module-specific conftest**: Place fixtures in `conftest.py` at the appropriate level; the
  root fixtures are described in [Fixtures](./endpoint-testing.md#fixtures)

---

## Test File Naming

### Use `test_` Prefix

All test files must start with `test_` to be discovered by pytest:

```python
# Good
test_chip.py
test_execution.py
test_flow_helpers.py

# Bad
chip_test.py           # Wrong suffix position
chip_tests.py          # Wrong suffix
test_chip_tests.py     # Redundant
```

### Match Source File Names

Test files should match the source file they test:

| Source File       | Test File              |
| ----------------- | ---------------------- |
| `chip.py`         | `test_chip.py`         |
| `execution.py`    | `test_execution.py`    |
| `flow_helpers.py` | `test_flow_helpers.py` |

---

## Test Class and Function Naming

### Class Naming

Group related tests using classes with descriptive names:

```python
# Good - Descriptive class names
class TestChipRouter:
    """Tests for chip-related API endpoints."""
    pass

class TestChipRouterListEndpoint:
    """Tests specifically for the list chips endpoint."""
    pass

class TestFlowSessionInitialization:
    """Test FlowSession initialization and basic setup."""
    pass

class TestFlowSessionParameterManagement:
    """Test parameter get/set operations."""
    pass

# Bad - Vague or incorrect naming
class ChipTests:              # Missing 'Test' prefix
class Test:                   # Too generic
class TestMisc:               # Not descriptive
```

### Function Naming

Test function names should describe the scenario being tested:

```python
# Good - Clear, descriptive names following pattern:
# test_<method>_<scenario>_<expected_result>

def test_list_chips_empty(self):
    """Test listing chips when no chips exist."""
    pass

def test_list_chips_with_data(self):
    """Test listing chips when chips exist."""
    pass

def test_list_chips_filters_by_user(self):
    """Test that listing chips only returns chips for the authenticated user."""
    pass

def test_fetch_chip_not_found(self):
    """Test fetching a non-existent chip returns 404."""
    pass

def test_create_chip_invalid_size(self):
    """Test creating a chip with invalid size returns 400."""
    pass

def test_update_nonexistent_qubit(self):
    """Test updating a non-existent qubit raises ValueError."""
    pass

# Bad - Vague or unclear names
def test_chip(self):              # Too vague
def test_1(self):                 # Not descriptive
def test_it_works(self):          # Not specific
def chip_list_test(self):         # Wrong prefix
```

### Naming Patterns

| Scenario           | Pattern                            | Example                           |
| ------------------ | ---------------------------------- | --------------------------------- |
| Happy path         | `test_<action>_success`            | `test_create_chip_success`        |
| Empty/no data      | `test_<action>_empty`              | `test_list_chips_empty`           |
| With data          | `test_<action>_with_data`          | `test_list_chips_with_data`       |
| Filtering          | `test_<action>_filters_by_<field>` | `test_list_chips_filters_by_user` |
| Not found          | `test_<action>_not_found`          | `test_fetch_chip_not_found`       |
| Invalid input      | `test_<action>_invalid_<field>`    | `test_create_chip_invalid_size`   |
| Duplicate/conflict | `test_<action>_duplicate`          | `test_create_chip_duplicate`      |
| Permission/access  | `test_<action>_wrong_user`         | `test_fetch_chip_wrong_user`      |
| Exception          | `test_<action>_raises_<exception>` | `test_update_nonexistent_qubit`   |

---

## Test Structure (AAA Pattern)

### Arrange-Act-Assert

All tests should follow the AAA (Arrange-Act-Assert) pattern. The `test_client` fixture used
here is defined in [Fixtures](./endpoint-testing.md#fixtures):

```python
def test_list_chips_with_data(self, test_client):
    """Test listing chips when chips exist."""
    # Arrange: Set up test data and preconditions
    chip = ChipDocument(
        chip_id="test_chip_001",
        username="test_user",
        size=64,
        qubits={},
        couplings={},
        system_info=SystemInfoModel(),
    )
    chip.insert()

    # Act: Execute the code under test
    response = test_client.get(
        "/api/chip",
        headers={"X-Username": "test_user"},
    )

    # Assert: Verify the results
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["chip_id"] == "test_chip_001"
    assert data[0]["size"] == 64
```

### Guidelines

- **Arrange**: Set up all preconditions and inputs
- **Act**: Execute the single action being tested
- **Assert**: Verify the expected outcomes
- **Comments**: Use `# Arrange`, `# Act`, `# Assert` comments for complex tests
- **Single action**: Each test should test one thing only

---

## Assertions

### Use Descriptive Assertion Messages

```python
# Good - With descriptive messages
assert retrieved_chip is not None, f"Chip with id '{chip_id}' should exist"
assert retrieved_chip.chip_id == chip_id, "Chip ID should match"
assert retrieved_chip.size == expected_size, f"Size should be {expected_size}"
assert len(retrieved_chip.qubits) == 2, "Should have 2 qubits"

# Bad - No messages
assert retrieved_chip is not None
assert retrieved_chip.chip_id == chip_id
```

### Common Assertion Patterns

```python
# Status code assertions
assert response.status_code == 200
assert response.status_code == 404
assert response.status_code == 400

# JSON response assertions
data = response.json()
assert len(data) == 1
assert data[0]["chip_id"] == "test_chip_001"
assert "not found" in response.json()["detail"].lower()

# Collection assertions
assert "Q0" in retrieved_chip.qubits, "Q0 should exist in qubits"
assert all(chip.username == username for chip in chips), "All chips should belong to user"

# Exception assertions
with pytest.raises(ValueError, match=f"Qubit {qubit_id} not found"):
    chip.update_qubit(qubit_id, new_qubit)

with pytest.raises(RuntimeError, match="No active calibration session"):
    get_session()
```

---

## Test Data Management

### Test Constants

Define constants at the module level:

```python
# Test constants
TEST_DATE = "2024-01-01T00:00:00Z"
TEST_USERNAME = "test_user"
```

### Helper Functions

Create helper functions for test data creation:

```python
def create_test_qubit(qid: str, x_180_length: float = 30.0) -> QubitModel:
    """Helper function to create a test qubit."""
    return QubitModel(
        username=TEST_USERNAME,
        chip_id="test_chip",
        status="active",
        qid=qid,
        data={"x_180_length": x_180_length},
    )


def create_test_coupling(qid: str) -> CouplingModel:
    """Helper function to create a test coupling."""
    return CouplingModel(
        username=TEST_USERNAME,
        chip_id="test_chip",
        status="active",
        qid=qid,
        data={},
    )
```

### Fixtures for Test Data

Fixture scopes and naming are covered in [Fixtures](./endpoint-testing.md#fixtures).

```python
@pytest.fixture
def system_info() -> SystemInfoModel:
    """Create test system info."""
    return SystemInfoModel(
        created_at=TEST_DATE,
        updated_at=TEST_DATE,
    )


@pytest.fixture
def sample_chip(system_info) -> ChipDocument:
    """Create a sample chip for testing."""
    return ChipDocument(
        chip_id="sample_chip",
        username=TEST_USERNAME,
        size=64,
        qubits={
            "Q0": create_test_qubit("Q0"),
            "Q1": create_test_qubit("Q1"),
        },
        system_info=system_info,
    )
```

---

## Coverage Guidelines

### Minimum Coverage Targets

| Component         | Target Coverage |
| ----------------- | --------------- |
| API Routers       | 80%             |
| Database Models   | 90%             |
| Workflow Helpers  | 75%             |
| Utility Functions | 90%             |

### What to Test

**Always test:**

- Happy path (successful operations)
- Error conditions (404, 400, validation errors)
- Edge cases (empty lists, boundary values)
- Access control (user isolation)
- Input validation

**Skip testing:**

- Third-party library internals
- Simple getters/setters without logic
- Trivial one-line functions

### Running Coverage

```bash
# Run tests with coverage
pytest --cov=src/qdash

# Generate HTML report
pytest --cov=src/qdash --cov-report=html

# Check specific module
pytest --cov=src/qdash/api tests/qdash/api/
```
