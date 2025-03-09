# ruff: noqa
import os
from contextlib import asynccontextmanager

from bunnet import init_bunnet
from qdash.dbmodel.document_models import document_models
from fastapi import FastAPI
from pymongo import MongoClient

from qdash.config import Settings, get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and close the database connection."""
    settings = get_settings()
    client: MongoClient = MongoClient(
        "mongo",  # Docker service name
        port=27017,  # Docker internal port
        username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
        password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
    )
    init_bunnet(
        database=client.qubex,
        document_models=document_models(),
    )
    yield
    client.close()
