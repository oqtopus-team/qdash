from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from qdash.api.db.session import lifespan
from qdash.api.lib.auth import get_current_active_user
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
# Auth router without global auth dependency (login/register/logout need to be public)
app.include_router(auth.router, tags=["auth"])

# Routers without auth (for direct browser access like images, file downloads)
# These routers handle their own auth for write operations
app.include_router(execution.router, tags=["execution"])
app.include_router(file.router, tags=["file"])

# All other routers with global auth dependency
auth_dependency = [Depends(get_current_active_user)]
app.include_router(calibration.router, tags=["calibration"], dependencies=auth_dependency)
app.include_router(settings.router, tags=["settings"], dependencies=auth_dependency)
app.include_router(chip.router, tags=["chip"], dependencies=auth_dependency)
app.include_router(task.router, tags=["task"], dependencies=auth_dependency)
app.include_router(parameter.router, tags=["parameter"], dependencies=auth_dependency)
app.include_router(tag.router, tags=["tag"], dependencies=auth_dependency)
app.include_router(device_topology.router, tags=["device_topology"], dependencies=auth_dependency)
app.include_router(backend.router, tags=["backend"], dependencies=auth_dependency)
app.include_router(flow.router, tags=["flow"], dependencies=auth_dependency)
app.include_router(flow_schedule.router, tags=["flow_schedule"], dependencies=auth_dependency)
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"], dependencies=auth_dependency)
