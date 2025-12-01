"""Root configuration for tests.

This module provides pytest fixtures for testing the QDash API.
It follows the Bunnet ODM testing patterns for MongoDB integration.

MongoDB connection options (in order of preference):
1. MONGO_TEST_DSN environment variable (for CI/CD or custom setup)
2. Docker Compose MongoDB service (mongo:27017)
"""

import os
from collections.abc import Generator
from dataclasses import dataclass

import pytest
from pymongo import MongoClient
from pymongo.database import Database

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Set async fixture loop scope
pytest.mark.asyncio_default_fixture_loop_scope = "function"


# Set test environment variables before importing app modules
os.environ.setdefault("ENV", "test")
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


@dataclass
class TestSettings:
    """Test configuration settings.

    Attributes
    ----------
    mongo_test_dsn : str
        MongoDB connection string for testing
    mongo_test_db : str
        Database name for testing

    """

    # Use 'mongo' hostname for devcontainer (Docker network)
    # Override with MONGO_TEST_DSN env var for other environments
    mongo_test_dsn: str = os.getenv("MONGO_TEST_DSN", "mongodb://root:example@mongo:27017")
    mongo_test_db: str = os.getenv("MONGO_TEST_DB", "qdash_test")


@pytest.fixture(scope="session")
def test_settings() -> TestSettings:
    """Get test settings.

    Returns
    -------
    TestSettings
        Test configuration instance

    """
    return TestSettings()


@pytest.fixture(scope="session")
def mongo_client(test_settings: TestSettings) -> Generator[MongoClient, None, None]:
    """Create MongoDB client for testing (session-scoped).

    This fixture connects to the MongoDB instance specified in test settings.
    By default, it connects to the Docker Compose MongoDB service.

    Parameters
    ----------
    test_settings : TestSettings
        Test configuration

    Yields
    ------
    MongoClient
        MongoDB client instance

    """
    client: MongoClient = MongoClient(test_settings.mongo_test_dsn)
    yield client
    client.close()


@pytest.fixture(scope="session")
def mongo_db(mongo_client: MongoClient, test_settings: TestSettings) -> Database:
    """Get MongoDB database for testing.

    Parameters
    ----------
    mongo_client : MongoClient
        MongoDB client
    test_settings : TestSettings
        Test configuration

    Returns
    -------
    Database
        MongoDB database instance

    """
    return mongo_client[test_settings.mongo_test_db]


@pytest.fixture
def init_db(
    mongo_client: MongoClient, test_settings: TestSettings
) -> Generator[Database, None, None]:
    """Initialize Bunnet with test database.

    This fixture sets up the database connection for Bunnet ODM
    and cleans up after each test.

    Parameters
    ----------
    mongo_client : MongoClient
        MongoDB client
    test_settings : TestSettings
        Test configuration

    Yields
    ------
    Database
        MongoDB database instance

    """
    from qdash.api.db.session import set_test_client

    set_test_client(mongo_client, db_name=test_settings.mongo_test_db)
    db = mongo_client[test_settings.mongo_test_db]
    yield db

    # Clean up: drop all collections after each test
    # Don't close the client as it's session-scoped
    for collection_name in db.list_collection_names():
        db.drop_collection(collection_name)


@pytest.fixture
def test_client(init_db):
    """FastAPI test client with test MongoDB.

    This fixture provides a TestClient instance that can be used
    to make requests to the API with a test database.

    Parameters
    ----------
    init_db : Database
        Initialized test database (automatically used via fixture dependency)

    Returns
    -------
    TestClient
        FastAPI test client

    """
    from fastapi.testclient import TestClient

    from qdash.api.main import app

    return TestClient(app)
