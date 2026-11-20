"""Tests for the FastAPI application factory."""

from typing import Any, cast

import pytest
from fastapi.middleware.cors import CORSMiddleware

from qdash.api.app import OPENAPI_EXTRA, create_app
from qdash.api.app.factory import _add_component_models
from qdash.config import Settings
from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec


def test_create_app_accepts_settings_for_cors_origins() -> None:
    settings = Settings.model_construct(
        env="production",
        client_url="",
        api_cors_origins=("https://app.example.com",),
        prefect_api_url="http://prefect.example.com",
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )

    app = create_app(settings=settings)

    cors_middleware = next(
        middleware
        for middleware in app.user_middleware
        if cast("Any", middleware.cls) is CORSMiddleware
    )
    assert cors_middleware.kwargs["allow_origins"] == ["https://app.example.com"]


def test_create_app_applies_api_metadata() -> None:
    settings = Settings.model_construct(
        env="production",
        client_url="",
        api_cors_origins=(),
        prefect_api_url="http://prefect.example.com",
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )

    app = create_app(settings=settings)
    openapi_schema = app.openapi()

    assert app.title == "QDash API"
    assert openapi_schema["info"]["license"]["name"] == "Apache 2.0"
    assert "/agent-sessions" in openapi_schema["paths"]
    assert openapi_schema["components"]["schemas"]
    assert (
        openapi_schema["components"]["securitySchemes"]["BearerAuth"]
        == OPENAPI_EXTRA["components"]["securitySchemes"]["BearerAuth"]
    )
    assert "HTTPBearer" in openapi_schema["components"]["securitySchemes"]
    assert openapi_schema["security"] == [{"BearerAuth": []}]
    assert app.openapi() is openapi_schema
    assert openapi_schema["security"] == [{"BearerAuth": []}]

    # Regenerating the schema must preserve security metadata without duplication.
    app.openapi_schema = None
    assert app.openapi() == openapi_schema


def test_openapi_extra_defines_bearer_auth() -> None:
    bearer_auth = OPENAPI_EXTRA["components"]["securitySchemes"]["BearerAuth"]

    assert bearer_auth["type"] == "http"
    assert bearer_auth["scheme"] == "bearer"


def _settings() -> Settings:
    return Settings.model_construct(
        env="production",
        client_url="",
        api_cors_origins=(),
        prefect_api_url="http://prefect.example.com",
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )


def test_openapi_publishes_the_pipeline_spec_without_changing_routes() -> None:
    schemas = create_app(settings=_settings()).openapi()["components"]["schemas"]

    spec = schemas["CalibrationPipelineSpec"]
    assert spec["properties"]["steps"]["items"]["discriminator"]["propertyName"] == "type"
    assert "CustomOneQubitStep" in schemas
    assert "PipelineTargets" in schemas
    # Requests keep a plain object, so the validate route still reports problems itself.
    assert schemas["ValidatePipelineRequest"]["properties"]["spec"]["type"] == "object"


def test_component_models_refuse_to_replace_another_model() -> None:
    schema: dict[str, Any] = {"components": {"schemas": {"TaskCall": {"type": "string"}}}}

    with pytest.raises(RuntimeError, match="TaskCall"):
        _add_component_models(schema, (CalibrationPipelineSpec,))
