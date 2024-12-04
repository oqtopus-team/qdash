from bunnet import init_bunnet
from dbmodel.bluefors import BlueforsModel
from dbmodel.cooling_down import CoolingDownModel
from dbmodel.execution_lock import ExecutionLockModel
from dbmodel.menu import MenuModel
from dbmodel.one_qubit_calib import OneQubitCalibModel
from dbmodel.qpu import QPUModel
from dbmodel.session_info import SessionInfoModel
from dbmodel.two_qubit_calib import TwoQubitCalibModel
from dbmodel.wiring_info import WiringInfoModel
from pymongo import MongoClient


def init_db():
    client: MongoClient = MongoClient(
        "localhost", 27017, username="root", password="example"
    )
    init_bunnet(
        database=client.cloud,
        document_models=[
            QPUModel,
            OneQubitCalibModel,
            TwoQubitCalibModel,
            MenuModel,
            ExecutionLockModel,
            BlueforsModel,
            SessionInfoModel,
            WiringInfoModel,
            CoolingDownModel,
        ],  # type: ignore
    )
