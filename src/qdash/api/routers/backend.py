"""Backend router for QDash API."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.backend import BackendResponseModel, ListBackendsResponse
from qdash.dbmodel.backend import BackendDocument

router = APIRouter()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@router.get(
    "/backends",
    response_model=ListBackendsResponse,
    summary="List all backends",
    description="Retrieve a list of all registered backends",
    operation_id="listBackends",
)
def list_backends(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ListBackendsResponse:
    """List all registered backends.

    Retrieves all backend configurations from the database. Backends represent
    quantum hardware or simulator configurations available for calibration
    workflows.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    ListBackendsResponse
        Wrapped list of all registered backend response models

    """
    logger.info(f"User {ctx.user.username} is listing backends for project {ctx.project_id}.")
    backends = BackendDocument.find({"project_id": ctx.project_id}).to_list()
    return ListBackendsResponse(
        backends=[BackendResponseModel(**backend.dict()) for backend in backends]
    )
