"""FastAPI application factory for QDash API."""

from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.models import Schema
from fastapi.routing import APIRoute
from fastapi.utils import deep_dict_update
from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import GenerateJsonSchema

from qdash.api.app.metadata import API_METADATA, OPENAPI_EXTRA
from qdash.api.app.router_registry import register_routers
from qdash.api.db.session import lifespan
from qdash.api.middleware.request_id import RequestIdMiddleware
from qdash.config import Settings, get_settings, resolve_api_cors_origins
from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec

# Models that request bodies carry as plain JSON objects but that clients should still get as
# typed models. Publishing them as components changes no route: ValidatePipelineRequest.spec
# stays dict[str, Any] so the validate route keeps reporting problems instead of answering 422.
OPENAPI_COMPONENT_MODELS: tuple[type[BaseModel], ...] = (CalibrationPipelineSpec,)


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


def _add_component_models(schema: dict[str, Any], models: tuple[type[BaseModel], ...]) -> None:
    """Add ``models`` and the models they reference to ``components.schemas``.

    The definitions are encoded as FastAPI encodes its own, so a model that a route already
    publishes yields an identical entry. A different model under a taken name raises instead of
    replacing the published one.
    """
    generator = GenerateJsonSchema(ref_template="#/components/schemas/{model}")
    _, definitions = generator.generate_definitions(
        inputs=[(model, "validation", TypeAdapter(model).core_schema) for model in models]
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in definitions.items():
        encoded = jsonable_encoder(
            Schema.model_validate(definition), by_alias=True, exclude_none=True
        )
        published = components.get(name)
        if published is not None and published != encoded:
            raise RuntimeError(f"OpenAPI component {name!r} already describes another model")
        components[name] = encoded


def _configure_openapi_schema(app: FastAPI) -> None:
    """Add API security metadata and normalize OpenAPI 3.1 schema details."""
    generate_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = generate_openapi()
        # FastAPI has already cached ``schema``; drop a partly transformed copy on failure
        # so the next call regenerates it and fails the same way.
        try:
            deep_dict_update(schema, deepcopy(OPENAPI_EXTRA))
            _add_component_models(schema, OPENAPI_COMPONENT_MODELS)
            _add_binary_formats(schema)
        except Exception:
            app.openapi_schema = None
            raise
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
