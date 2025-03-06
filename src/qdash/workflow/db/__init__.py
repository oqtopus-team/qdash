import os

from bunnet import init_bunnet
from pymongo import MongoClient
from qdash.dbmodel.bluefors import BlueforsModel
from qdash.dbmodel.execution_lock import ExecutionLockModel
from qdash.dbmodel.execution_run import ExecutionRunModel
from qdash.dbmodel.experiment import ExperimentModel
from qdash.dbmodel.experiment_history import ExperimentHistoryModel
from qdash.dbmodel.fridge_status import FridgeStatusModel

mongo_ip = os.getenv("MONGO_HOST")
client: MongoClient = MongoClient(mongo_ip, 27017, username="root", password="example")
# client: MongoClient = MongoClient(mongo_uri)
# client: MongoClient = MongoClient(
#     "localhost", 27017, username="root", password="example"
# )
# client: MongoClient = MongoClient(mongo_uri)
init_bunnet(
    database=client.cloud,
    document_models=[
        BlueforsModel,
        ExecutionLockModel,
        ExperimentHistoryModel,
        ExperimentModel,
        ExecutionRunModel,
        FridgeStatusModel,
    ],  # type: ignore
)
