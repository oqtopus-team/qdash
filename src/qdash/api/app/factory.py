"""FastAPI application factory for QDash API."""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from qdash.api.app.metadata import API_METADATA, OPENAPI_EXTRA
from qdash.api.app.router_registry import register_routers
from qdash.api.db.session import lifespan
from qdash.api.middleware.request_id import RequestIdMiddleware
from qdash.config import Settings, get_settings, resolve_api_cors_origins


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate a unique id for the route."""
    return f"{route.tags[0]}-{route.name}"


def _add_binary_formats(value: Any) -> None:
    """Make OpenAPI 3.1 binary strings consumable by OpenAPI generators."""
    if isinstance(value, dict):
        if (
            value.get("type") == "string"
            and value.get("contentMediaType") == "application/octet-stream"
        ):
            value.setdefault("format", "binary")
        for child in value.values():
            _add_binary_formats(child)
    elif isinstance(value, list):
        for child in value:
            _add_binary_formats(child)


def _configure_openapi_schema(app: FastAPI) -> None:
    """Normalize generator-sensitive OpenAPI 3.1 schema details."""
    generate_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        schema = generate_openapi()
        _add_binary_formats(schema)
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the QDash API app."""
    app = FastAPI(
        **API_METADATA,
        generate_unique_id_function=custom_generate_unique_id,
        separate_input_output_schemas=False,
        lifespan=lifespan,
        root_path="/api",
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
        openapi_extra=OPENAPI_EXTRA,
    )

    app_settings = settings or get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolve_api_cors_origins(app_settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_routers(app)
    _configure_openapi_schema(app)

    return app
