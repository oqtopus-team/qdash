import os
from contextlib import asynccontextmanager

from bunnet import init_bunnet
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from pymongo import MongoClient
from qdash.api.routers import (
    auth,
    calibration,
    chip,
    execution,
    file,
    fridges,
    menu,
    settings,
    task,
)
from qdash.dbmodel.bluefors import BlueforsModel
from qdash.dbmodel.execution_lock import ExecutionLockModel


def custom_generate_unique_id(route: APIRoute):
    return f"{route.tags[0]}-{route.name}"


mongo_host = os.getenv("MONGO_HOST")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client: MongoClient = MongoClient(mongo_host, 27017, username="root", password="example")
    init_bunnet(
        database=client.cloud,
        document_models=[
            BlueforsModel,
            ExecutionLockModel,
        ],  # type: ignore
    )
    yield
    client.close()


# APIキーヘッダーのセキュリティスキーマを含むFastAPIアプリケーションを作成
app = FastAPI(
    title="QDash Server",
    description="API for QDash",
    summary="QDash API",
    version="0.0.1",
    contact={
        "name": "QDash",
        "email": "oqtopus-team@googlegroups.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    generate_unique_id_function=custom_generate_unique_id,
    separate_input_output_schemas=False,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "auth", "description": "Authentication operations"},
        {"name": "calibration", "description": "Calibration operations"},
        {"name": "chip", "description": "Chip operations"},
        {"name": "execution", "description": "Execution operations"},
        {"name": "experiment", "description": "Experiment operations"},
        {"name": "file", "description": "File operations"},
        {"name": "fridges", "description": "Fridge operations"},
        {"name": "menu", "description": "Menu operations"},
        {"name": "qpu", "description": "QPU operations"},
        {"name": "settings", "description": "Settings operations"},
        {"name": "task", "description": "Task operations"},
        {"name": "executionV2", "description": "Execution V2 operations"},
    ],
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    openapi_extra={
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Username",
                    "description": "Optional username header for authentication",
                }
            }
        },
        "security": [{"ApiKeyAuth": []}],
    },
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
app.include_router(settings.router, tags=["settings"])
app.include_router(fridges.router, tags=["fridges"])
app.include_router(execution.router, tags=["execution"])
app.include_router(chip.router, tags=["chip"])
app.include_router(file.router, tags=["file"])
app.include_router(auth.router, tags=["auth", "authentication"])
app.include_router(task.router, tags=["task"])
