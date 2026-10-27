"""Shared Qubex box catalog endpoints (administrators only)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from qdash.api.dependencies import get_config_boxes_service
from qdash.api.lib.auth import get_admin_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.config_boxes import (
    ConfigBox,
    ListConfigBoxesResponse,
    UpsertConfigBoxResponse,
)
from qdash.api.services.config_boxes_service import ConfigBoxesError, ConfigBoxesService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/config/boxes",
    response_model=ListConfigBoxesResponse,
    summary="List the control boxes in box.yaml",
    operation_id="listConfigBoxes",
)
def list_config_boxes(
    _admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[ConfigBoxesService, Depends(get_config_boxes_service)],
    chip_id: Annotated[
        str | None, Query(description="Chip whose box.yaml to read in the legacy layout")
    ] = None,
) -> ListConfigBoxesResponse:
    """The catalog shared by every chip, plus the box types qubex accepts."""
    return service.list_boxes(chip_id=chip_id)


@router.post(
    "/config/boxes",
    response_model=UpsertConfigBoxResponse,
    summary="Register or update a control box in box.yaml",
    operation_id="upsertConfigBox",
)
def upsert_config_box(
    box: ConfigBox,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[ConfigBoxesService, Depends(get_config_boxes_service)],
) -> UpsertConfigBoxResponse:
    """Write the entry and publish it; other entries and comments are kept.

    Raises
    ------
    HTTPException
        400 for an unknown type, a missing address or adapter, or the legacy layout.

    """
    try:
        return service.upsert_box(username=admin.username, box=box)
    except ConfigBoxesError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
