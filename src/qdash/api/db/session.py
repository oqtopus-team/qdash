"""Database session management with dependency injection support."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from bunnet import init_bunnet
from fastapi import FastAPI
from pymongo import MongoClient
from pymongo.database import Database

from qdash.dbmodel.document_models import document_models

# Global client and database references
_client: MongoClient[Any] | None = None
_database: Database[Any] | None = None


def get_mongo_client() -> MongoClient[Any]:
    """Get or create MongoDB client.

    Returns
    -------
    MongoClient
        MongoDB client instance

    """
    global _client
    if _client is None:
        mongo_host = os.getenv("MONGO_HOST", "mongo")
        # MONGO_PORT is for host-side port mapping. Inside the Docker network,
        # MongoDB always listens on 27017.
        mongo_port = 27017 if mongo_host == "mongo" else int(os.getenv("MONGO_PORT", "27017"))
        _client = MongoClient(
            mongo_host,
            port=mongo_port,
            username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
            password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
        )
    return _client


def get_database() -> Database[Any]:
    """Get MongoDB database instance.

    Returns
    -------
    Database
        MongoDB database instance

    """
    global _database
    if _database is None:
        db_name = os.getenv("MONGO_DB_NAME", "qdash")
        _database = get_mongo_client()[db_name]
    return _database


def init_db(database: Database[Any] | None = None) -> None:
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


def set_test_client(client: MongoClient[Any], db_name: str = "test_db") -> None:
    """Set test MongoDB client (for mongomock).

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


_ADMIN_INIT_MAX_ATTEMPTS = 3


def create_initial_admin() -> None:
    """Create initial admin user from environment variables if not exists.

    Environment variables:
    - QDASH_ADMIN_USERNAME: Admin username (required)
    - QDASH_ADMIN_PASSWORD: Admin password (required)

    If both are set and the user doesn't exist, creates the admin user
    with a default project. On every startup the admin's default project is
    checked and repaired: a missing project is created, and a missing or
    inactive owner membership on an admin-owned project is restored.

    Several API worker processes run this during startup at the same time.
    The unique indexes on users, projects and memberships decide which worker
    creates each row; a worker that loses an insert race reuses the row the
    other worker created. A duplicate key error that does not correspond to
    a row created by another worker is re-raised. Existing rows are changed
    only through targeted field updates, so concurrent edits to other fields
    are preserved.
    """
    import logging
    import secrets

    from pymongo.errors import DuplicateKeyError

    from qdash.api.lib.auth import get_password_hash
    from qdash.datamodel.system_info import SystemInfoModel
    from qdash.datamodel.user import SystemRole, generate_user_id
    from qdash.dbmodel.user import UserDocument

    logger = logging.getLogger(__name__)

    admin_username = os.getenv("QDASH_ADMIN_USERNAME", "").strip()
    admin_password = os.getenv("QDASH_ADMIN_PASSWORD")

    if not admin_username or not admin_password:
        return

    if UserDocument.find_one({"username": admin_username}).run() is None:
        user = UserDocument(
            user_id=generate_user_id(),
            username=admin_username,
            hashed_password=get_password_hash(admin_password),
            access_token=secrets.token_urlsafe(32),
            display_name="Administrator",
            system_role=SystemRole.ADMIN,
            system_info=SystemInfoModel(),
        )
        try:
            user.insert()
        except DuplicateKeyError:
            # Another worker may have inserted the same username first. Any
            # other unique-key conflict leaves no such user and is re-raised.
            if UserDocument.find_one({"username": admin_username}).run() is None:
                raise
            logger.info("Initial admin user '%s' was created by another worker", admin_username)
        else:
            logger.info("Created initial admin user: %s", admin_username)
    else:
        logger.debug("Initial admin user '%s' already exists", admin_username)

    for attempt in range(1, _ADMIN_INIT_MAX_ATTEMPTS + 1):
        try:
            if _ensure_admin_default_project(admin_username):
                return
            # The default project pointer changed after it was read.
            reason = "default project was changed concurrently"
        except DuplicateKeyError:
            # Another worker inserted the project or the membership; the next
            # attempt reads that row instead of inserting.
            if attempt == _ADMIN_INIT_MAX_ATTEMPTS:
                raise
            reason = "default project is being created concurrently"
        if attempt == _ADMIN_INIT_MAX_ATTEMPTS:
            msg = f"Could not initialize default project for admin '{admin_username}': {reason}"
            raise RuntimeError(msg)
        logger.info(
            "Retrying default project initialization for admin '%s' (%s; attempt %d/%d)",
            admin_username,
            reason,
            attempt,
            _ADMIN_INIT_MAX_ATTEMPTS,
        )


def _ensure_admin_default_project(admin_username: str) -> bool:
    """Ensure the admin has a usable default project.

    A default project the admin owns gets an active owner membership. A
    default project owned by someone else is kept when the admin is an
    active member and is never given an owner membership. Otherwise the
    admin's conventionally named project is reused or created and set as the
    default, unless that name belongs to a project with a different owner ID.

    Returns ``False`` when the default project pointer changed after it was
    read, so the caller can retry with fresh state. Raises
    ``DuplicateKeyError`` when an insert loses a race.
    """
    import logging

    from qdash.common.utils.datetime import now
    from qdash.dbmodel.project import ProjectDocument
    from qdash.dbmodel.project_membership import ProjectMembershipDocument
    from qdash.dbmodel.user import UserDocument

    logger = logging.getLogger(__name__)

    user = UserDocument.find_one({"username": admin_username}).run()
    if user is None:
        msg = f"Initial admin user '{admin_username}' disappeared during initialization"
        raise RuntimeError(msg)

    current_default = user.default_project_id
    project = ProjectDocument.find_by_id(current_default) if current_default else None
    if project is not None:
        if project.owner_user_id == user.user_id:
            _ensure_owner_membership(project.project_id, user.user_id, admin_username)
            return True
        if ProjectMembershipDocument.get_active_membership(
            project.project_id, admin_username, user.user_id
        ):
            return True
        logger.warning(
            "Default project %s of admin '%s' is owned by '%s' and the admin is not an "
            "active member; using the admin's own project instead",
            project.project_id,
            admin_username,
            project.owner_username,
        )

    project_name = f"{admin_username}'s project"
    project = ProjectDocument.find_one(
        {"owner_username": admin_username, "name": project_name}
    ).run()
    if project is None:
        project = ProjectDocument(
            owner_user_id=user.user_id, owner_username=admin_username, name=project_name
        )
        project.insert()
        logger.info("Created default project %s for admin: %s", project.project_id, admin_username)
    elif project.owner_user_id != user.user_id:
        # For example a project left by a deleted account with the same
        # username. Ownership is not transferred automatically.
        logger.error(
            "Project '%s' (%s) belongs to user ID %s, not admin '%s' (%s); "
            "leaving the admin's default project unchanged",
            project_name,
            project.project_id,
            project.owner_user_id,
            admin_username,
            user.user_id,
        )
        return True

    # Make the project usable before pointing the admin at it.
    _ensure_owner_membership(project.project_id, user.user_id, admin_username)
    if current_default == project.project_id:
        return True
    result = UserDocument.get_motor_collection().update_one(
        {"user_id": user.user_id, "default_project_id": current_default},
        {"$set": {"default_project_id": project.project_id, "system_info.updated_at": now()}},
    )
    if result.matched_count == 0:
        return False
    logger.info("Set default project %s for admin: %s", project.project_id, admin_username)
    return True


def _ensure_owner_membership(project_id: str, user_id: str, username: str) -> None:
    """Insert or reactivate the owner membership of an admin-owned project.

    Raises ``DuplicateKeyError`` when another worker inserts the membership
    first. An existing row is updated in place, which also repairs a stale
    user ID left by an earlier account with the same username.
    """
    from qdash.common.utils.datetime import now
    from qdash.datamodel.project import ProjectRole
    from qdash.dbmodel.project_membership import ProjectMembershipDocument

    key = {"project_id": project_id, "username": username}
    membership = ProjectMembershipDocument.find_one(key).run()
    if membership is None:
        ProjectMembershipDocument(
            project_id=project_id,
            user_id=user_id,
            username=username,
            role=ProjectRole.OWNER,
            status="active",
        ).insert()
        return
    if (
        membership.user_id == user_id
        and membership.role == ProjectRole.OWNER
        and membership.status == "active"
    ):
        return
    ProjectMembershipDocument.get_motor_collection().update_one(
        key,
        {
            "$set": {
                "user_id": user_id,
                "role": ProjectRole.OWNER.value,
                "status": "active",
                "system_info.updated_at": now(),
            }
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize and close the database connection.

    Parameters
    ----------
    app : FastAPI
        FastAPI application instance

    """
    from qdash.api.logging_config import setup_logging

    setup_logging()
    init_db()
    create_initial_admin()
    try:
        yield
    finally:
        close_db()
