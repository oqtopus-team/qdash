import os

from bunnet import init_bunnet
from pymongo import MongoClient
from qdash.dbmodel.bluefors import BlueforsModel
from qdash.dbmodel.cooling_down import CoolingDownModel
from qdash.dbmodel.execution_lock import ExecutionLockModel
from qdash.dbmodel.execution_run import ExecutionRunModel
from qdash.dbmodel.execution_run_history import ExecutionRunHistoryModel
from qdash.dbmodel.experiment import ExperimentModel
from qdash.dbmodel.experiment_history import ExperimentHistoryModel
from qdash.dbmodel.fridge_status import FridgeStatusModel
from qdash.dbmodel.menu import MenuModel
from qdash.dbmodel.one_qubit_calib import OneQubitCalibModel
from qdash.dbmodel.one_qubit_calib_all_history import OneQubitCalibAllHistoryModel
from qdash.dbmodel.one_qubit_calib_daily_summary import OneQubitCalibDailySummaryModel
from qdash.dbmodel.one_qubit_calib_history import OneQubitCalibHistoryModel
from qdash.dbmodel.one_qubit_calib_history_all import OneQubitCalibHistoryAllModel
from qdash.dbmodel.qpu import QPUModel
from qdash.dbmodel.session_info import SessionInfoModel
from qdash.dbmodel.two_qubit_calib import TwoQubitCalibModel
from qdash.dbmodel.two_qubit_calib_daily_summary import TwoQubitCalibDailySummaryModel
from qdash.dbmodel.two_qubit_calib_history import TwoQubitCalibHistoryModel
from qdash.dbmodel.wiring_info import WiringInfoModel

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
        OneQubitCalibModel,
        TwoQubitCalibModel,
        MenuModel,
        OneQubitCalibHistoryModel,
        OneQubitCalibDailySummaryModel,
        TwoQubitCalibHistoryModel,
        TwoQubitCalibDailySummaryModel,
        SessionInfoModel,
        WiringInfoModel,
        QPUModel,
        BlueforsModel,
        OneQubitCalibHistoryAllModel,
        ExecutionLockModel,
        ExperimentHistoryModel,
        ExperimentModel,
        ExecutionRunModel,
        ExecutionRunHistoryModel,
        FridgeStatusModel,
        OneQubitCalibAllHistoryModel,
        CoolingDownModel,
    ],  # type: ignore
)
