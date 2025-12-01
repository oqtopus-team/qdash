from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.api.lib.auth import get_optional_current_user
from qdash.api.schemas.auth import User
from qdash.config import Settings, get_settings

router = APIRouter()
logger = getLogger("uvicorn.app")


@router.get(
    "/settings",
    response_model=Settings,
    summary="Get settings",
    description="Get settings from the server",
    operation_id="fetch_config",
)
def fetchConfig(
    settings: Annotated[Settings, Depends(get_settings)],
    _current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
):
    return settings
