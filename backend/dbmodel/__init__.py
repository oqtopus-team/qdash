# import os

# from bunnet import init_bunnet
# from dbmodel.bluefors import BlueforsModel
# from dbmodel.execution_lock import ExecutionLockModel
# from dbmodel.execution_run import ExecutionRunModel
# from dbmodel.execution_run_history import ExecutionRunHistoryModel
# from dbmodel.experiment import ExperimentModel
# from dbmodel.experiment_history import ExperimentHistoryModel
# from dbmodel.fridge_status import FridgeStatusModel
# from dbmodel.menu import MenuModel
# from dbmodel.one_qubit_calib import OneQubitCalibModel
# from dbmodel.one_qubit_calib_all_history import OneQubitCalibAllHistoryModel
# from dbmodel.one_qubit_calib_daily_summary import OneQubitCalibDailySummaryModel
# from dbmodel.one_qubit_calib_history import OneQubitCalibHistoryModel
# from dbmodel.one_qubit_calib_history_all import OneQubitCalibHistoryAllModel
# from dbmodel.qpu import QPUModel
# from dbmodel.session_info import SessionInfoModel
# from dbmodel.two_qubit_calib import TwoQubitCalibModel
# from dbmodel.two_qubit_calib_daily_summary import TwoQubitCalibDailySummaryModel
# from dbmodel.two_qubit_calib_history import TwoQubitCalibHistoryModel
# from dbmodel.wiring_info import WiringInfoModel
# from pymongo import MongoClient

# mongo_ip = os.getenv("MONGO_HOST")
# client: MongoClient = MongoClient(mongo_ip, 27017, username="root", password="example")
# # client: MongoClient = MongoClient(mongo_uri)
# # client: MongoClient = MongoClient(
# #     "localhost", 27017, username="root", password="example"
# # )
# # client: MongoClient = MongoClient(mongo_uri)
# init_bunnet(
#     database=client.cloud,
#     document_models=[
#         OneQubitCalibModel,
#         TwoQubitCalibModel,
#         MenuModel,
#         OneQubitCalibHistoryModel,
#         OneQubitCalibDailySummaryModel,
#         TwoQubitCalibHistoryModel,
#         TwoQubitCalibDailySummaryModel,
#         SessionInfoModel,
#         WiringInfoModel,
#         QPUModel,
#         BlueforsModel,
#         OneQubitCalibHistoryAllModel,
#         ExecutionLockModel,
#         ExperimentHistoryModel,
#         ExperimentModel,
#         ExecutionRunModel,
#         ExecutionRunHistoryModel,
#         FridgeStatusModel,
#         OneQubitCalibAllHistoryModel,
#     ],  # type: ignore
# )
