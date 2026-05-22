"""FastAPI application assembly helpers."""

from qdash.api.app.factory import create_app, custom_generate_unique_id
from qdash.api.app.metadata import API_METADATA, OPENAPI_EXTRA
from qdash.api.app.router_registry import (
    PROTECTED_ROUTERS,
    PUBLIC_ROUTERS,
    RouterRegistration,
    register_routers,
)

__all__ = [
    "API_METADATA",
    "OPENAPI_EXTRA",
    "PROTECTED_ROUTERS",
    "PUBLIC_ROUTERS",
    "RouterRegistration",
    "create_app",
    "custom_generate_unique_id",
    "register_routers",
]
