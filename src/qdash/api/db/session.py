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

    """
    global _database
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and close the database connection.

    Parameters
    ----------
    app : FastAPI
        FastAPI application instance

    """
    init_db()
    yield
    close_db()
