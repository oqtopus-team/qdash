"""FastAPI application factory for QDash API."""

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

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return app
