"""Settings router for QDash API."""

from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends

from qdash.api.schemas.settings import SettingsResponse
from qdash.config import Settings
from qdash.config import get_settings as get_settings_dependency

router = APIRouter()
logger = getLogger("uvicorn.app")


@router.get(
    "/settings",
    response_model=SettingsResponse,
    summary="Get settings",
    description="Get settings from the server",
    operation_id="getSettings",
)
def get_settings(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> SettingsResponse:
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
    SettingsResponse
        Current non-secret server configuration settings

    """
    return SettingsResponse.model_validate(settings, from_attributes=True)
