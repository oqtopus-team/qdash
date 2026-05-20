import logging
import os
from typing import Any

from bunnet import init_bunnet
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import OperationFailure

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
        mongo_host = os.getenv("MONGO_HOST", "mongo")
        mongo_port = 27017 if mongo_host == "mongo" else int(os.getenv("MONGO_PORT", "27017"))
        _client = MongoClient(
            mongo_host,
            port=mongo_port,
            username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
            password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
        )
    return _client


# Track if already initialized
_initialized = False


def _prepare_flow_indexes(database: Database[Any]) -> None:
    """Prepare legacy flow indexes before Bunnet creates current indexes."""
    collection = database["flows"]
    index_info = collection.index_information()
    legacy_index = index_info.get("project_id_1_name_1")
    if not legacy_index or legacy_index.get("unique") is True:
        return

    duplicates = list(
        collection.aggregate(
            [
                {
                    "$group": {
                        "_id": {"project_id": "$project_id", "name": "$name"},
                        "count": {"$sum": 1},
                        "ids": {"$push": "$_id"},
                    }
                },
                {"$match": {"count": {"$gt": 1}}},
                {"$limit": 5},
            ]
        )
    )
    if duplicates:
        raise RuntimeError(
            "Cannot create unique flow index because duplicate flow names exist "
            f"within a project: {duplicates}"
        )

    try:
        collection.drop_index("project_id_1_name_1")
        logger.info("Dropped legacy non-unique flow index project_id_1_name_1")
    except OperationFailure as exc:
        if exc.code != 27:  # IndexNotFound; another worker may have already dropped it.
            raise


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

    db_name = os.getenv("MONGO_DB_NAME", "qdash")
    database = _get_client()[db_name]
    _prepare_flow_indexes(database)
    init_bunnet(
        database=database,
        document_models=document_models(),
    )

    _initialized = True


def force_reinitialize() -> None:
    """Force re-initialization of MongoDB connection.

    This is needed in forked subprocess scenarios (e.g., Dask workers with
    processes=True) where the parent process's MongoDB client is not fork-safe.
    The _initialized flag carries over from the parent but the connection is stale.
    """
    global _initialized, _client
    _initialized = False
    _client = None
    initialize()
