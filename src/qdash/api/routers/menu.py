import logging
from typing import Annotated, ClassVar

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.error import (
    Detail,
    NotFoundErrorResponse,
)
from qdash.api.schemas.exception import InternalSeverError
from qdash.datamodel.menu import MenuModel
from qdash.datamodel.task import TaskModel
from qdash.neodbmodel.menu import MenuDocument
from qdash.neodbmodel.task import TaskDocument

router = APIRouter()


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ListMenuResponse(BaseModel):
    """ListMenuResponse is a Pydantic model that represents a menu item."""

    menus: list[MenuModel]


class CreateMenuRequest(MenuModel):
    """CreateMenuRequest is a Pydantic model for creating a menu item."""

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "example": {
                "name": "CheckOneQubit",
                "username": "admin",
                "description": "This is a sample menu item.",
                "qids": [["28", "29"]],
                "notify_bool": False,
                "tasks": [
                    "CheckStatus",
                    "DumpBox",
                    "CheckNoise",
                    "CheckRabi",
                    "CreateHPIPulse",
                    "CheckHPIPulse",
                    "CreatePIPulse",
                    "CheckPIPulse",
                    "CheckT1",
                    "CheckT2Echo",
                ],
                "tags": ["debug"],
            }
        }
    }


class CreateMenuResponse(BaseModel):
    """CreateMenuResponse is a Pydantic model for the create menu response."""

    name: str


class UpdateMenuRequest(MenuModel):
    """UpdateMenuRequest is a Pydantic model for updating a menu item."""


class UpdateMenuResponse(BaseModel):
    """UpdateMenuResponse is a Pydantic model for the update menu response."""

    name: str


class DeleteMenuResponse(BaseModel):
    """DeleteMenuResponse is a Pydantic model for the delete menu response."""

    name: str


class GetMenuResponse(MenuModel):
    """GetMenuResponse is a Pydantic model for the get menu response."""


@router.get(
    "/menu",
    response_model=ListMenuResponse,
    summary="Retrieve a list of menu items.",
    operation_id="list_menu",
)
def list_menu(current_user: Annotated[User, Depends(get_current_active_user)]) -> ListMenuResponse:
    """Retrieve a list of menu items.

    Returns
    -------
        ListMenuResponse: A response containing the list of menu items.

    """
    menus = MenuDocument.find({"username": current_user.username}).run()
    menu_list = []
    for menu in menus:
        menu_item = MenuModel(
            name=menu.name,
            username=menu.username,
            description=menu.description,
            qids=menu.qids,
            tasks=menu.tasks,
            notify_bool=menu.notify_bool,
            tags=menu.tags,
            task_details=menu.task_details,
        )
        menu_list.append(menu_item)
    return ListMenuResponse(menus=menu_list)


@router.post(
    "/menu",
    response_model=CreateMenuResponse,
    summary="Create a new menu item.",
    operation_id="create_menu",
)
def create_menu(
    request: CreateMenuRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CreateMenuResponse:
    """Create a new menu item.

    Args:
    ----
        request (CreateMenuRequest): The request object containing the menu item details.
        current_user (User): The current authenticated user.

    Returns:
    -------
        CreateMenuResponse: The response object containing the name of the created menu item.

    """
    task_details = {}
    for task_name in request.tasks:
        task_doc = TaskDocument.find_one({"name": task_name}).run()
        task = TaskModel(
            name=task_doc.name,
            username=task_doc.username,
            description=task_doc.description,
            task_type=task_doc.task_type,
            input_parameters=task_doc.input_parameters,
            output_parameters=task_doc.output_parameters,
        )
        task_details[task_name] = task

    menu_doc = MenuDocument(
        name=request.name,
        username=current_user.username,
        description=request.description,
        qids=request.qids,
        tasks=request.tasks,
        notify_bool=request.notify_bool,
        tags=request.tags,
        task_details=task_details,
    )
    try:
        menu_doc.save()
    except Exception as e:
        logger.error(f"Failed to save menu: {e}")
        raise InternalSeverError(detail=f"Failed to save menu: {e!s}")
    return CreateMenuResponse(name=menu_doc.name)


check_one_qubit_preset = MenuModel(
    name="CheckOneQubitShort",
    username="",
    description="check one qubit characteristics short",
    qids=[["28", "29", "30", "31"]],
    notify_bool=False,
    tasks=[
        "CheckStatus",
        "DumpBox",
        "CheckNoise",
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CreatePIPulse",
        "CheckPIPulse",
        "CheckT1",
        "CheckT2Echo",
    ],
    tags=["debug"],
    task_details={},
)

one_qubit_coarse_preset = MenuModel(
    name="OneQubitCoarse",
    username="",
    description="check one qubit characteristics coarse",
    qids=[["28", "29", "30", "31"]],
    notify_bool=False,
    tasks=[
        "DumpBox",
        "CheckNoise",
        "CheckStatus",
        "CheckQubitFrequency",
        "CheckReadoutFrequency",
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CreatePIPulse",
        "CheckPIPulse",
        "CheckT1",
        "CheckT2Echo",
    ],
    tags=["debug"],
    task_details={},
)

one_qubit_fine_preset = MenuModel(
    name="OneQubitFine",
    username="",
    description="check one qubit characteristics fine",
    qids=[["28", "29", "30", "31"]],
    notify_bool=False,
    tasks=[
        "CheckEffectiveQubitFrequency",
        "CheckDRAGHPIPulse",
        "CheckDRAGPIPulse",
        "CreateDRAGHPIPulse",
        "CreateDRAGPIPulse",
        "ReadoutClassification",
        "RandomizedBenchmarking",
        "X90InterleavedRandomizedBenchmarking",
        "X180InterleavedRandomizedBenchmarking",
    ],
    tags=["debug"],
    task_details={},
)


@router.get(
    "/menu/preset",
    response_model=ListMenuResponse,
    summary="Retrieve a list of preset menu items.",
    operation_id="listPreset",
    responses={404: {"model": Detail}},
)
def list_preset(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ListMenuResponse:
    """Retrieve a list of preset menu items.

    Returns
    -------
        ListMenuResponse: A response containing the list of preset menu items.

    """
    menu_list = [check_one_qubit_preset, one_qubit_coarse_preset, one_qubit_fine_preset]
    task_docs = TaskDocument.find({"username": current_user.username}).run()
    task_map = {
        doc.name: TaskModel(
            name=doc.name,
            username=doc.username,
            description=doc.description,
            task_type=doc.task_type,
            input_parameters=doc.input_parameters,
            output_parameters=doc.output_parameters,
        )
        for doc in task_docs
    }
    logger.debug(f"task_map: {task_map}")
    for menu in menu_list:
        menu.username = current_user.username
        menu.task_details = {task_name: task_map.get(task_name) for task_name in menu.tasks}
    return ListMenuResponse(menus=menu_list)


@router.get(
    "/menu/{name}",
    response_model=GetMenuResponse,
    summary="Retrieve a menu by its name.",
    responses={404: {"model": Detail}},
    operation_id="get_menu_by_name",
)
def get_menu_by_name(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> GetMenuResponse | NotFoundErrorResponse:
    """Retrieve a menu by its name.

    Args:
    ----
        name (str): The name of the menu.
        current_user (User): The current authenticated user.

    Returns:
    -------
        GetMenuResponse: The response containing the menu details.

    Raises:
    ------
        InternalServerError: If there is an error retrieving the menu.
        NotFoundErrorResponse: If the menu is not found.

    """
    try:
        menu = MenuDocument.find_one({"name": name, "username": current_user.username}).run()
    except Exception as e:
        logger.error(f"Failed to get menu: {e}")
        raise InternalSeverError(detail=f"Failed to get menu: {e!s}")
    if menu is None:
        return NotFoundErrorResponse(detail=f"menu not found: {name}")
    return GetMenuResponse(
        name=menu.name,
        username=menu.username,
        description=menu.description,
        qids=menu.qids,
        tasks=menu.tasks,
        notify_bool=menu.notify_bool,
        tags=menu.tags,
        task_details=menu.task_details,
    )


@router.put(
    "/menu/{name}",
    response_model=UpdateMenuResponse,
    responses={404: {"model": Detail}},
    summary="Update a menu with the given name.",
    operation_id="update_menu",
)
def update_menu(
    name: str,
    req: UpdateMenuRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UpdateMenuResponse | NotFoundErrorResponse:
    """Update a menu with the given name.

    Args:
    ----
        name (str): The name of the menu to update.
        req (UpdateMenuRequest): The request object containing the updated menu data.
        current_user (User): The current authenticated user.

    Returns:
    -------
        Union[UpdateMenuResponse, NotFoundErrorResponse]: The response object indicating the success of the update or an error if the menu is not found.

    """
    existing_menu = MenuDocument.find_one({"name": name, "username": current_user.username}).run()
    if existing_menu:
        existing_menu.name = req.name
        existing_menu.description = req.description
        existing_menu.qids = req.qids
        existing_menu.tasks = req.tasks
        existing_menu.notify_bool = req.notify_bool
        existing_menu.tags = req.tags
        existing_menu.task_details = req.task_details
        existing_menu.save()
        return UpdateMenuResponse(name=existing_menu.name)
    logger.warning(f"menu not found: {name}")
    return NotFoundErrorResponse(detail=f"menu not found: {name}")


@router.delete(
    "/menu/{name}",
    response_model=DeleteMenuResponse,
    responses={404: {"model": Detail}},
    summary="Delete a menu by its name.",
    operation_id="delete_menu",
)
def delete_menu(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> DeleteMenuResponse | NotFoundErrorResponse:
    """Delete a menu by its name.

    Args:
    ----
        name (str): The name of the menu to be deleted.
        current_user (User): The current authenticated user.

    Returns:
    -------
        DeleteMenuResponse | NotFoundErrorResponse: The response indicating the success or failure of the deletion.

    """
    existing_menu = MenuDocument.find_one({"name": name, "username": current_user.username}).run()
    if existing_menu is not None:
        existing_menu.delete()
        return DeleteMenuResponse(name=existing_menu.name)
    logger.warning(f"menu not found: {name}")
    return NotFoundErrorResponse(detail=f"menu not found: {name}")
