import os
from contextlib import asynccontextmanager

from bunnet import init_bunnet
from dbmodel.bluefors import BlueforsModel
from dbmodel.cooling_down import CoolingDownModel
from dbmodel.execution_lock import ExecutionLockModel
from dbmodel.execution_run_history import ExecutionRunHistoryModel
from dbmodel.experiment import ExperimentModel
from dbmodel.experiment_history import ExperimentHistoryModel
from dbmodel.instrument import InstrumentModel
from dbmodel.menu import MenuModel
from dbmodel.one_qubit_calib import OneQubitCalibModel
from dbmodel.one_qubit_calib_all_history import OneQubitCalibAllHistoryModel
from dbmodel.one_qubit_calib_daily_summary import OneQubitCalibDailySummaryModel
from dbmodel.one_qubit_calib_history import OneQubitCalibHistoryModel
from dbmodel.qpu import QPUModel
from dbmodel.qube import QubeModel
from dbmodel.session_info import SessionInfoModel
from dbmodel.two_qubit_calib import TwoQubitCalibModel
from dbmodel.two_qubit_calib_daily_summary import TwoQubitCalibDailySummaryModel
from dbmodel.two_qubit_calib_history import TwoQubitCalibHistoryModel
from dbmodel.wiring_info import WiringInfoModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from pymongo import MongoClient
from server.routers import (
    calibration,
    execution,
    experiment,
    fridges,
    menu,
    qpu,
    settings,
)


def custom_generate_unique_id(route: APIRoute):
    return f"{route.tags[0]}-{route.name}"


mongo_host = os.getenv("MONGO_HOST")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client: MongoClient = MongoClient(
        mongo_host, 27017, username="root", password="example"
    )
    init_bunnet(
        database=client.cloud,
        document_models=[
            OneQubitCalibModel,
            TwoQubitCalibModel,
            OneQubitCalibHistoryModel,
            TwoQubitCalibHistoryModel,
            OneQubitCalibDailySummaryModel,
            TwoQubitCalibDailySummaryModel,
            MenuModel,
            QubeModel,
            QPUModel,
            SessionInfoModel,
            WiringInfoModel,
            CoolingDownModel,
            InstrumentModel,
            BlueforsModel,
            ExecutionLockModel,
            ExperimentHistoryModel,
            ExperimentModel,
            ExecutionRunHistoryModel,
            OneQubitCalibAllHistoryModel,
            CoolingDownModel,
        ],  # type: ignore
    )
    yield
    client.close()


app = FastAPI(
    title="QDash Server",
    description="API for QDash",
    summary="QDash API",
    version="0.0.1",
    contact={
        "name": "QDash",
        "email": "oqtopus-team[at]googlegroups.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    # openapi_url="/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    separate_input_output_schemas=False,
    lifespan=lifespan,
)


origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(calibration.router, tags=["calibration"])
app.include_router(menu.router, tags=["menu"])
app.include_router(qpu.router, tags=["qpu"])
app.include_router(settings.router, tags=["settings"])
app.include_router(fridges.router, tags=["fridges"])
app.include_router(execution.router, tags=["execution"])
app.include_router(experiment.router, tags=["experiment"])
