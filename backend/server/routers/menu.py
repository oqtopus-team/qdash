from logging import getLogger
from typing import Annotated

from datamodel.menu import MenuModel
from fastapi import APIRouter, Depends
from neodbmodel.initialize import initialize
from neodbmodel.menu import MenuDocument
from pydantic import BaseModel
from server.lib.auth import get_current_active_user
from server.schemas.auth import User
from server.schemas.error import (
    Detail,
    NotFoundErrorResponse,
)
from server.schemas.exception import InternalSeverError

router = APIRouter()
logger = getLogger("uvicorn.app")


class ListMenuResponse(BaseModel):
    """ListMenuResponse is a Pydantic model that represents a menu item."""

    menus: list[MenuModel]


class CreateMenuRequest(MenuModel):
    """CreateMenuRequest is a Pydantic model for creating a menu item."""


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
    initialize()
    menus = MenuDocument.find({"username": current_user.username}).run()
    menu_list = []
    for menu in menus:
        menu_item = MenuModel(
            name=menu.name,
            username=menu.username,
            description=menu.description,
            qids=menu.qids,
            notify_bool=menu.notify_bool,
            tags=menu.tags,
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
    initialize()
    menu_doc = MenuDocument(
        name=request.name,
        username=current_user.username,
        description=request.description,
        qids=request.qids,
        notify_bool=request.notify_bool,
        tags=request.tags,
    )
    try:
        menu_doc.save()
    except Exception as e:
        logger.error(f"Failed to save menu: {e}")
        raise InternalSeverError(detail=f"Failed to save menu: {e!s}")
    return CreateMenuResponse(name=menu_doc.name)


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
    initialize()
    existing_menu = MenuDocument.find_one({"name": name, "username": current_user.username}).run()
    if existing_menu is not None:
        existing_menu.delete()
        return DeleteMenuResponse(name=existing_menu.name)
    logger.warning(f"menu not found: {name}")
    return NotFoundErrorResponse(detail=f"menu not found: {name}")


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
    initialize()
    existing_menu = MenuDocument.find_one({"name": name, "username": current_user.username}).run()
    if existing_menu:
        existing_menu.name = req.name
        existing_menu.description = req.description
        existing_menu.qids = req.qids
        existing_menu.notify_bool = req.notify_bool
        existing_menu.tags = req.tags
        existing_menu.save()
        return UpdateMenuResponse(name=existing_menu.name)
    logger.warning(f"menu not found: {name}")
    return NotFoundErrorResponse(detail=f"menu not found: {name}")


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
        initialize()
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
        notify_bool=menu.notify_bool,
        tags=menu.tags,
    )
