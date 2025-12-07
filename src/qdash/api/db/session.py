"""Database session management with dependency injection support."""

import os
from contextlib import asynccontextmanager

from bunnet import init_bunnet
from fastapi import FastAPI
from pymongo import MongoClient
from pymongo.database import Database
from qdash.dbmodel.document_models import document_models

# Global client and database references
_client: MongoClient | None = None
_database: Database | None = None


def get_mongo_client() -> MongoClient:
    """Get or create MongoDB client.

    Returns
    -------
    MongoClient
        MongoDB client instance

    """
    global _client
    if _client is None:
        # Note: MONGO_PORT is for host-side port mapping, not container-to-container communication
        # MongoDB always listens on 27017 inside the Docker network
        _client = MongoClient(
            os.getenv("MONGO_HOST", "mongo"),
            port=27017,
            username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
            password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
        )
    return _client


def get_database() -> Database:
    """Get MongoDB database instance.

    Returns
    -------
    Database
        MongoDB database instance

    """
    global _database
    if _database is None:
        _database = get_mongo_client().qubex
    return _database


def init_db(database: Database | None = None) -> None:
    """Initialize Bunnet with given or default database.

    Parameters
    ----------
    database : Database | None
        Optional database instance. If None, uses default.

    Note
    ----
    If _database is already set (e.g., by set_test_client), this function
    will skip reinitialization to preserve test database settings.
    In test mode (ENV=test), always skip if already initialized.

    """
    global _database
    # Skip if already initialized (preserves test database setting)
    if _database is not None:
        return
    # In test mode, set_test_client should be called before this
    if os.getenv("ENV") == "test":
        return
    db = database or get_database()
    _database = db
    init_bunnet(database=db, document_models=document_models())


def set_test_client(client: MongoClient, db_name: str = "test_db") -> None:
    """Set test MongoDB client (for mongomock or testcontainers).

    Parameters
    ----------
    client : MongoClient
        MongoDB client instance (can be mongomock.MongoClient)
    db_name : str
        Database name to use for testing

    """
    global _client, _database
    _client = client
    _database = client[db_name]
    init_bunnet(database=_database, document_models=document_models())


def close_db() -> None:
    """Close MongoDB connection and reset global state."""
    global _client, _database
    if _client:
        _client.close()
    _client = None
    _database = None


def create_initial_admin() -> None:
    """Create initial admin user from environment variables if not exists.

    Environment variables:
    - QDASH_ADMIN_USERNAME: Admin username (required)
    - QDASH_ADMIN_PASSWORD: Admin password (required)

    If both are set and the user doesn't exist, creates the admin user
    with a default project.
    """
    import logging
    import secrets

    from passlib.context import CryptContext
    from qdash.api.lib.project_service import ProjectService
    from qdash.datamodel.system_info import SystemInfoModel
    from qdash.datamodel.user import SystemRole
    from qdash.dbmodel.user import UserDocument

    logger = logging.getLogger(__name__)

    admin_username = os.getenv("QDASH_ADMIN_USERNAME", "").strip()
    admin_password = os.getenv("QDASH_ADMIN_PASSWORD")

    if not admin_username or not admin_password:
        return

    # Check if user already exists
    existing_user = UserDocument.find_one({"username": admin_username}).run()
    if existing_user:
        logger.debug(f"Initial admin user '{admin_username}' already exists")
        return

    # Create password hash
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash(admin_password)
    access_token = secrets.token_urlsafe(32)

    # Create admin user
    user = UserDocument(
        username=admin_username,
        hashed_password=hashed_password,
        access_token=access_token,
        full_name="Administrator",
        system_role=SystemRole.ADMIN,
        system_info=SystemInfoModel(),
    )
    user.insert()
    logger.info(f"Created initial admin user: {admin_username}")

    # Create default project for admin
    service = ProjectService()
    project = service.create_project(
        owner_username=admin_username,
        name=f"{admin_username}'s project",
    )
    user.default_project_id = project.project_id
    user.save()
    logger.info(f"Created default project for admin: {admin_username}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and close the database connection.

    Parameters
    ----------
    app : FastAPI
        FastAPI application instance

    """
    init_db()
    create_initial_admin()
    yield
    close_db()
