from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from qdash.api.db.session import lifespan
from qdash.api.lib.auth import get_current_active_user
from qdash.api.middleware.request_id import RequestIdMiddleware
from qdash.api.routers import (
    admin,
    auth,
    backend,
    calibration,
    chip,
    config,
    copilot,
    device_topology,
    execution,
    file,
    flow,
    issue,
    issue_knowledge,
    metrics,
    project,
    provenance,
    settings,
    tag,
    task,
    task_file,
    task_result,
    topology,
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
    root_path="/api",
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
app.add_middleware(RequestIdMiddleware)
# Auth router without global auth dependency (login/register/logout need to be public)
app.include_router(auth.router, tags=["auth"])

# Admin router (has its own admin auth via get_admin_user dependency)
app.include_router(admin.router, tags=["admin"])

# Project router (has its own auth handling via dependencies)
app.include_router(project.router, tags=["projects"])

# Routers without auth (for direct browser access like images, file downloads)
# These routers handle their own auth for write operations
app.include_router(execution.router, tags=["execution"])
app.include_router(file.router, tags=["file"])
app.include_router(copilot.public_router, prefix="/copilot", tags=["copilot"])
app.include_router(issue.public_router, tags=["issue"])

# All other routers with global auth dependency
auth_dependency = [Depends(get_current_active_user)]
app.include_router(calibration.router, tags=["calibration"], dependencies=auth_dependency)
app.include_router(
    copilot.router, prefix="/copilot", tags=["copilot"], dependencies=auth_dependency
)
app.include_router(settings.router, tags=["settings"], dependencies=auth_dependency)
app.include_router(chip.router, tags=["chip"], dependencies=auth_dependency)
app.include_router(task.router, tags=["task"], dependencies=auth_dependency)
app.include_router(task_file.router, tags=["task-file"], dependencies=auth_dependency)
app.include_router(task_result.router, tags=["task-result"], dependencies=auth_dependency)
app.include_router(issue.router, tags=["issue"], dependencies=auth_dependency)
app.include_router(issue_knowledge.router, tags=["issue-knowledge"], dependencies=auth_dependency)
app.include_router(tag.router, tags=["tag"], dependencies=auth_dependency)
app.include_router(device_topology.router, tags=["device-topology"], dependencies=auth_dependency)
app.include_router(backend.router, tags=["backend"], dependencies=auth_dependency)
app.include_router(flow.router, tags=["flow"], dependencies=auth_dependency)
app.include_router(
    metrics.router, prefix="/metrics", tags=["metrics"], dependencies=auth_dependency
)
app.include_router(
    topology.router, prefix="/topology", tags=["topology"], dependencies=auth_dependency
)
app.include_router(config.router, tags=["config"], dependencies=auth_dependency)
app.include_router(
    provenance.router, prefix="/provenance", tags=["provenance"], dependencies=auth_dependency
)
