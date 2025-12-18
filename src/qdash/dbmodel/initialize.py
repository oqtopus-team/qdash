import logging
import os
from typing import Any

from bunnet import init_bunnet
from pymongo import MongoClient
from qdash.config import get_settings
from qdash.dbmodel.document_models import document_models

settings = get_settings()
logger = logging.getLogger(__name__)

# Skip MongoDB connection in test mode - tests set up their own connection
_client: MongoClient[Any] | None = None


def _get_client() -> MongoClient[Any]:
    """Get or create MongoDB client (lazy initialization)."""
    global _client
    if _client is None:
        _client = MongoClient(
            "mongo",  # Docker service name
            port=27017,  # Docker internal port
            username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
            password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
        )
    return _client


# Track if already initialized
_initialized = False


def initialize() -> None:
    """Initialize the repository and create initial data if needed.

    Note
    ----
    In test mode (ENV=test), this function skips initialization as tests
    set up their own database connection via set_test_client().

    """
    global _initialized

    # Skip if already initialized
    if _initialized:
        return

    # Skip in test mode - tests use set_test_client() to configure the database
    if os.getenv("ENV") == "test":
        return

    init_bunnet(
        database=_get_client().qubex,
        document_models=document_models(),
    )

    _initialized = True
