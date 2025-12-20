"""Root configuration for tests.

This module provides pytest fixtures for testing the QDash API.
It uses mongomock for in-memory MongoDB testing, eliminating the need
for a real MongoDB instance.
"""

import os
import sys
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

# Mock prefect module before any imports
# This is necessary because prefect has pydantic version conflicts with qubex
if "prefect" not in sys.modules:

    def _mock_decorator(*args: Any, **kwargs: Any) -> Any:
        """Mock decorator that handles both @decorator and @decorator() syntax."""
        if len(args) == 1 and callable(args[0]) and not kwargs:
            # Called as @decorator without parentheses
            return args[0]
        # Called as @decorator() with parentheses
        return lambda f: f

    prefect_mock = MagicMock()
    prefect_mock.flow = _mock_decorator
    prefect_mock.task = _mock_decorator
    prefect_mock.get_run_logger = MagicMock(return_value=MagicMock())
    sys.modules["prefect"] = prefect_mock
    sys.modules["prefect.client"] = MagicMock()
    sys.modules["prefect.client.orchestration"] = MagicMock()
    sys.modules["prefect.client.schemas"] = MagicMock()
    sys.modules["prefect.client.schemas.actions"] = MagicMock()
    sys.modules["prefect.client.schemas.filters"] = MagicMock()
    sys.modules["prefect.client.schemas.schedules"] = MagicMock()
    sys.modules["prefect.deployments"] = MagicMock()
    sys.modules["prefect.exceptions"] = MagicMock()
    sys.modules["prefect.states"] = MagicMock()

import mongomock
import pytest
from pymongo.database import Database

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Set async fixture loop scope
pytest.mark.asyncio_default_fixture_loop_scope = "function"  # type: ignore[attr-defined]


# Force test environment - override any existing value
# This must be set before importing any app modules
os.environ["ENV"] = "test"
os.environ.setdefault("CLIENT_URL", "http://localhost:3000")
os.environ.setdefault("PREFECT_API_URL", "http://localhost:4200/api")
os.environ.setdefault("SLACK_BOT_TOKEN", "test-token")
os.environ.setdefault("SLACK_CHANNEL_ID", "test-channel")
os.environ.setdefault("POSTGRES_DATA_PATH", "/tmp/postgres")
os.environ.setdefault("MONGO_DATA_PATH", "/tmp/mongo")
os.environ.setdefault("CALIB_DATA_PATH", "/tmp/calib")
os.environ.setdefault("QPU_DATA_PATH", "/tmp/qpu")
os.environ.setdefault("SLACK_APP_TOKEN", "test-app-token")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")


def _patched_command(self: Any, command: dict | str, **kwargs: Any) -> dict:
    """Patch mongomock's command method to support Bunnet's buildInfo call."""
    if isinstance(command, str):
        command = {command: 1}
    if "ping" in command:
        return {"ok": 1.0}
    if "buildInfo" in command:
        # Return mock MongoDB version info for Bunnet initialization
        return {
            "version": "6.0.0",
            "versionArray": [6, 0, 0, 0],
            "ok": 1.0,
        }
    if "create" in command:
        # Support collection creation
        return {"ok": 1.0}
    if "listIndexes" in command:
        # Support index listing
        return {"cursor": {"firstBatch": [], "id": 0, "ns": ""}, "ok": 1.0}
    if "createIndexes" in command:
        # Support index creation
        return {"ok": 1.0}
    # Default: return ok for other commands
    return {"ok": 1.0}


@pytest.fixture
def init_db() -> Generator[Database, None, None]:
    """Initialize Bunnet with in-memory mongomock database.

    This fixture sets up an in-memory MongoDB using mongomock,
    eliminating the need for a real MongoDB instance.

    Yields
    ------
    Database
        In-memory MongoDB database instance

    """
    import qdash.api.db.session as db_session
    from qdash.api.db.session import set_test_client

    # Reset global database reference before setting up test database
    db_session._database = None

    # Create in-memory MongoDB client using mongomock
    client = mongomock.MongoClient()
    db_name = "qdash_test"

    # Patch mongomock's command method to support Bunnet
    with patch.object(mongomock.Database, "command", _patched_command):
        set_test_client(client, db_name=db_name)
        db = client[db_name]
        yield db

    # Clean up: drop all collections after each test
    for collection_name in db.list_collection_names():
        db.drop_collection(collection_name)
    client.close()


@pytest.fixture
def test_client(init_db):
    """FastAPI test client with in-memory MongoDB.

    This fixture provides a TestClient instance that can be used
    to make requests to the API with an in-memory database.

    Parameters
    ----------
    init_db : Database
        Initialized in-memory database (automatically used via fixture dependency)

    Returns
    -------
    TestClient
        FastAPI test client

    """
    from fastapi.testclient import TestClient

    from qdash.api.main import app

    return TestClient(app)
