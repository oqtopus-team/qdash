from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from qdash.api.db.session import lifespan
from qdash.api.routers import (
    auth,
    calibration,
    chip,
    execution,
    file,
    menu,
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
app.include_router(execution.router, tags=["execution"])
app.include_router(chip.router, tags=["chip"])
app.include_router(file.router, tags=["file"])
app.include_router(auth.router, tags=["auth"])
app.include_router(task.router, tags=["task"])
app.include_router(parameter.router, tags=["parameter"])
app.include_router(tag.router, tags=["tag"])
