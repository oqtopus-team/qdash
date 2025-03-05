import os

from bunnet import init_bunnet
from pymongo import MongoClient
from qdash.neodbmodel.chip import ChipDocument
from qdash.neodbmodel.coupling import CouplingDocument
from qdash.neodbmodel.execution_history import ExecutionHistoryDocument
from qdash.neodbmodel.menu import MenuDocument
from qdash.neodbmodel.parameter import ParameterDocument
from qdash.neodbmodel.qubit import QubitDocument
from qdash.neodbmodel.task import TaskDocument
from qdash.neodbmodel.task_result_history import TaskResultHistoryDocument
from qdash.neodbmodel.user import UserDocument

mongo_ip = os.getenv("MONGO_HOST")
client: MongoClient = MongoClient(mongo_ip, 27017, username="root", password="example")  # noqa: S106


def initialize() -> None:
    """Initialize the repository and create initial data if needed."""
    init_bunnet(
        database=client.qubex,
        document_models=[
            ExecutionHistoryDocument,
            TaskResultHistoryDocument,
            QubitDocument,
            ChipDocument,
            ParameterDocument,
            TaskDocument,
            CouplingDocument,
            UserDocument,
            MenuDocument,
        ],
    )
