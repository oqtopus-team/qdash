import os

from bunnet import init_bunnet
from neodbmodel.chip import ChipDocument
from neodbmodel.execution_history import ExecutionHistoryDocument
from neodbmodel.parameter import ParameterDocument
from neodbmodel.qubit import QubitDocument
from neodbmodel.task import TaskDocument
from neodbmodel.task_history import TaskHistoryDocument
from pymongo import MongoClient

mongo_ip = os.getenv("MONGO_HOST")
client: MongoClient = MongoClient(mongo_ip, 27017, username="root", password="example")  # noqa: S106


def initialize() -> None:
    """Initialize the repository."""
    init_bunnet(
        database=client.qubex,
        document_models=[
            ExecutionHistoryDocument,
            TaskHistoryDocument,
            QubitDocument,
            ChipDocument,
            ParameterDocument,
            TaskDocument,
        ],
    )
