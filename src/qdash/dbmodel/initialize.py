import os

from bunnet import init_bunnet
from pymongo import MongoClient
from qdash.config import get_settings
from qdash.dbmodel.document_models import document_models

settings = get_settings()
client: MongoClient = MongoClient(
    "mongo",  # Docker service name
    port=27017,  # Docker internal port
    username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
    password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
)


def initialize() -> None:
    """Initialize the repository and create initial data if needed."""
    init_bunnet(
        database=client.qubex,
        document_models=document_models(),
    )
