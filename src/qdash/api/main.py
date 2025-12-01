from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from qdash.api.db.session import lifespan
from qdash.api.routers import (
    auth,
    backend,
    calibration,
    chip,
    device_topology,
    execution,
    file,
    flow,
    flow_schedule,
    metrics,
    parameter,
    settings,
    tag,
    task,
)


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate a unique id for the route."""
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title="QDash API",
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
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    openapi_extra={
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Bearer token authentication. Use the access_token from login response.",
                }
            }
        },
        "security": [{"BearerAuth": []}],
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
app.include_router(calibration.router, prefix="/api", tags=["calibration"])
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(execution.router, prefix="/api", tags=["execution"])
app.include_router(chip.router, prefix="/api", tags=["chip"])
app.include_router(file.router, prefix="/api", tags=["file"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(task.router, prefix="/api", tags=["task"])
app.include_router(parameter.router, prefix="/api", tags=["parameter"])
app.include_router(tag.router, prefix="/api", tags=["tag"])
app.include_router(device_topology.router, prefix="/api", tags=["device_topology"])
app.include_router(backend.router, prefix="/api", tags=["backend"])
app.include_router(flow.router, prefix="/api", tags=["flow"])
app.include_router(flow_schedule.router, prefix="/api", tags=["flow_schedule"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])
