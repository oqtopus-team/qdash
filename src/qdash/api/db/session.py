# ruff: noqa
import os
from contextlib import asynccontextmanager

from bunnet import init_bunnet
from qdash.neodbmodel.document_models import document_models
from fastapi import FastAPI
from pymongo import MongoClient

mongo_host = os.getenv("MONGO_HOST")
username = "root"
password = "example"
port = 27017


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and close the database connection."""
    client: MongoClient = MongoClient(mongo_host, port=port, username=username, password=password)
    init_bunnet(
        database=client.qubex,
        document_models=document_models(),
    )
    yield
    client.close()
