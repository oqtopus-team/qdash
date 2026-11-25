"""Tests for the FastAPI application factory."""

from copy import deepcopy
from typing import Any, cast

import pytest
from fastapi.middleware.cors import CORSMiddleware

from qdash.api.app import OPENAPI_EXTRA, create_app, factory
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


def test_openapi_publishes_optional_list_queries_as_plain_arrays() -> None:
    paths = create_app(settings=_settings()).openapi()["paths"]

    def query(path: str, name: str) -> dict[str, Any]:
        parameters = paths[path]["get"]["parameters"]
        return cast("dict[str, Any]", next(p for p in parameters if p["name"] == name))

    status = query("/agent-sessions", "status")
    assert status["required"] is False
    assert status["schema"]["type"] == "array"
    assert status["schema"]["items"] == {"$ref": "#/components/schemas/AgentSessionStatus"}
    assert "anyOf" not in status["schema"]
    assert status["schema"]["description"] == "Only sessions in these statuses"
    for path, name in [
        ("/calibration-sessions", "status"),
        ("/calibration-sessions", "origin"),
        ("/chips/{chip_id}/qubits", "qids"),
        ("/provenance/changes", "parameter_names"),
        ("/provenance/degradation-trends", "parameter_names"),
    ]:
        assert query(path, name)["schema"]["type"] == "array", (path, name)
    # A scalar that may be null keeps its null branch.
    chip_id = query("/agent-sessions", "chip_id")
    assert {"type": "null"} in chip_id["schema"]["anyOf"]


def test_plain_optional_query_arrays_leaves_other_schemas_alone() -> None:
    nullable_list = {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]}
    schema: dict[str, Any] = {
        "paths": {
            "/x": {
                "get": {
                    "parameters": [
                        {
                            "name": "required",
                            "in": "query",
                            "required": True,
                            "schema": deepcopy(nullable_list),
                        },
                        {"name": "header", "in": "header", "schema": deepcopy(nullable_list)},
                        {
                            "name": "defaulted",
                            "in": "query",
                            "schema": {**deepcopy(nullable_list), "default": ["a"]},
                        },
                        {
                            "name": "mixed",
                            "in": "query",
                            "schema": {"anyOf": [{"type": "array"}, {"type": "string"}]},
                        },
                        {
                            "name": "list",
                            "in": "query",
                            "schema": {**deepcopy(nullable_list), "title": "L"},
                        },
                    ]
                }
            }
        }
    }
    original = deepcopy(schema)

    factory._plain_optional_query_arrays(schema)

    parameters = schema["paths"]["/x"]["get"]["parameters"]
    assert parameters[:4] == original["paths"]["/x"]["get"]["parameters"][:4]
    assert parameters[4]["schema"] == {"type": "array", "items": {"type": "string"}, "title": "L"}


def test_component_models_refuse_to_replace_another_model() -> None:
    schema: dict[str, Any] = {"components": {"schemas": {"TaskCall": {"type": "string"}}}}

    with pytest.raises(RuntimeError, match="TaskCall"):
        _add_component_models(schema, (CalibrationPipelineSpec,))


def test_a_failed_schema_transformation_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    # TaskCall is a component of the pipeline spec; publishing another TaskCall conflicts.
    conflict = {"components": {"schemas": {"TaskCall": {"type": "string"}}}}
    monkeypatch.setattr(factory, "OPENAPI_EXTRA", conflict)
    app = create_app(settings=_settings())

    with pytest.raises(RuntimeError, match="TaskCall"):
        app.openapi()
    assert app.openapi_schema is None
    with pytest.raises(RuntimeError, match="TaskCall"):
        app.openapi()

    # Without the conflict the transformed schema is cached as usual.
    monkeypatch.setattr(factory, "OPENAPI_EXTRA", OPENAPI_EXTRA)
    schema = app.openapi()
    assert "PipelineTargets" in schema["components"]["schemas"]
    assert app.openapi() is schema
