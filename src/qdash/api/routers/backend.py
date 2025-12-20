"""Backend router for QDash API."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.backend import BackendResponseModel, ListBackendsResponse
from qdash.repository.backend import MongoBackendRepository

router = APIRouter()
logger = logging.getLogger(__name__)


def get_backend_repository() -> MongoBackendRepository:
    """Get backend repository instance."""
    return MongoBackendRepository()


@router.get(
    "/backends",
    response_model=ListBackendsResponse,
    summary="List all backends",
    description="Retrieve a list of all registered backends",
    operation_id="listBackends",
)
def list_backends(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    backend_repo: Annotated[MongoBackendRepository, Depends(get_backend_repository)],
) -> ListBackendsResponse:
    """List all registered backends.

    Retrieves all backend configurations from the database. Backends represent
    quantum hardware or simulator configurations available for calibration
    workflows.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    backend_repo : MongoBackendRepository
        Repository for backend operations

    Returns
    -------
    ListBackendsResponse
        Wrapped list of all registered backend response models

    """
    logger.info(f"User {ctx.user.username} is listing backends for project {ctx.project_id}.")
    backends = backend_repo.list_by_project(ctx.project_id)
    return ListBackendsResponse(backends=[BackendResponseModel(**backend) for backend in backends])
