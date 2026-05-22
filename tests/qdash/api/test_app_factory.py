"""Tests for the FastAPI application factory."""

from typing import Any, cast

from fastapi.middleware.cors import CORSMiddleware

from qdash.api.app_factory import create_app
from qdash.config import Settings


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
