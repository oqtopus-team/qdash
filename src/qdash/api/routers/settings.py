"""Settings router for QDash API."""

from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.config import Settings, get_settings

router = APIRouter()
logger = getLogger("uvicorn.app")


@router.get(
    "/settings",
    response_model=Settings,
    summary="Get settings",
    description="Get settings from the server",
    operation_id="getSettings",
)
def get_settings_endpoint(settings: Annotated[Settings, Depends(get_settings)]):
    """Get server configuration settings.

    Retrieves the current server configuration including API ports, database
    connection settings, Prefect configuration, and other environment-specific
    settings.

    Parameters
    ----------
    settings : Settings
        Server settings injected via dependency

    Returns
    -------
    Settings
        Current server configuration settings

    """
    return settings
