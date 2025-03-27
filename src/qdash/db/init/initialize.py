"""Database initialization module."""

import os

from bunnet import init_bunnet
from pymongo import MongoClient
from qdash.dbmodel.document_models import document_models

mongo_ip = os.getenv("MONGO_HOST")
mongo_port = os.getenv("MONGO_PORT")
client: MongoClient = MongoClient(mongo_ip, int(mongo_port), username="root", password="example")  # noqa: S106


def initialize() -> None:
    """Initialize the repository and create initial data if needed."""
    init_bunnet(
        database=client.qubex,
        document_models=document_models(),
    )
