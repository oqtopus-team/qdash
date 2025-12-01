import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.api.lib.auth import get_optional_current_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.backend import BackendResponseModel
from qdash.dbmodel.backend import BackendDocument

router = APIRouter()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@router.get(
    "/backend",
    response_model=list[BackendResponseModel],
    summary="Get all backends",
    description="Retrieve a list of all registered backends",
    operation_id="fetchAllBackends",
)
def get_backends(
    current_user: Annotated[User, Depends(get_optional_current_user)],
) -> list[BackendResponseModel]:
    """Get all backends.

    Returns
    -------
    list[BackendResponseModel]
        A list of backend response models.

    """
    logger.info(f"User {current_user.username} is fetching all backends.")
    # Fetch all backend documents from the database
    backends = BackendDocument.find_all().to_list()
    return [BackendResponseModel(**backend.dict()) for backend in backends]
