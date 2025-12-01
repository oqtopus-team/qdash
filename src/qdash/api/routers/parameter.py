from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.parameter import ListParameterResponse
from qdash.datamodel.parameter import ParameterModel
from qdash.dbmodel.parameter import ParameterDocument

router = APIRouter()

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@router.get(
    "/parameter",
    summary="Fetch all parameters",
    operation_id="fetchAllParameters",
    response_model=ListParameterResponse,
)
def fetch_all_parameters(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ListParameterResponse:
    """Fetch all parameters.

    Args:
    ----
        current_user (User): The current user.

    Returns: ListParameterResponse
    -------

    """
    parameters = ParameterDocument.find({"username": current_user.username}).run()
    params = [
        ParameterModel(
            username=param.username,
            name=param.name,
            unit=param.unit,
            description=param.description,
        )
        for param in parameters
    ]
    return ListParameterResponse(parameters=params)
