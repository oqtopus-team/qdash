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
    """Get server settings."""
    return settings
