"""FastAPI application factory for QDash API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from qdash.api.db.session import lifespan
from qdash.api.middleware.request_id import RequestIdMiddleware
from qdash.api.router_registry import register_routers
from qdash.config import get_settings, resolve_api_cors_origins


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate a unique id for the route."""
    return f"{route.tags[0]}-{route.name}"


def create_app() -> FastAPI:
    """Create and configure the QDash API app."""
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
                        "description": (
                            "Bearer token authentication. Use the access_token from login response."
                        ),
                    }
                }
            },
            "security": [{"BearerAuth": []}],
        },
    )

    app_settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolve_api_cors_origins(app_settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_routers(app)

    return app
