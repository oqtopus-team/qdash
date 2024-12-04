from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends

from server.config import Settings, get_settings

router = APIRouter()
logger = getLogger("uvicorn.app")


@router.get(
    "/settings",
    response_model=Settings,
    summary="Get settings",
    description="Get settings from the server",
    operation_id="fetch_config",
)
def fetchConfig(settings: Annotated[Settings, Depends(get_settings)]):
    return settings
