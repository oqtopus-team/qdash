from logging import getLogger

from dbmodel.menu import MenuModel
from fastapi import APIRouter
from server.schemas.error import (
    Detail,
    NotFoundErrorResponse,
)
from server.schemas.exception import InternalSeverError
from server.schemas.menu import (
    CreateMenuRequest,
    CreateMenuResponse,
    DeleteMenuResponse,
    GetMenuResponse,
    ListMenuResponse,
    UpdateMenuRequest,
    UpdateMenuResponse,
)

router = APIRouter()
logger = getLogger("uvicorn.app")


@router.get(
    "/menu",
    response_model=list[ListMenuResponse],
    summary="Retrieve a list of menu items.",
    operation_id="list_menu",
)
def list_menu() -> list[ListMenuResponse]:
    """
    Retrieve a list of menu items.

    Returns:
        ListMenuResponse: A response containing the list of menu items.
    """
    try:
        menu_list = MenuModel.find_all().to_list()
    except Exception as e:
        logger.error(f"Failed to list menu: {e}")
        raise InternalSeverError(detail=f"Failed to list menu: {str(e)}")
    if menu_list is None:
        return list[ListMenuResponse]
    menu_list_response = []
    for menu in menu_list:
        menu_list_response.append(
            ListMenuResponse(
                name=menu.name,
                description=menu.description,
                one_qubit_calib_plan=menu.one_qubit_calib_plan,
                two_qubit_calib_plan=menu.two_qubit_calib_plan,
                mode=menu.mode,
                notify_bool=menu.notify_bool,
                flow=menu.flow,
                exp_list=menu.exp_list,
                tags=menu.tags,
            )
        )
    return menu_list_response


@router.post(
    "/menu",
    response_model=CreateMenuResponse,
    summary="Create a new menu item.",
    operation_id="create_menu",
)
def create_menu(request: CreateMenuRequest) -> CreateMenuResponse:
    """
    Create a new menu item.

    Args:
        request (CreateMenuRequest): The request object containing the menu item details.

    Returns:
        CreateMenuResponse: The response object containing the ID of the created menu item.
    """
    menu_model = MenuModel(**request.model_dump())
    try:
        menu_model.save()
    except Exception as e:
        logger.error(f"Failed to save menu: {e}")
        raise InternalSeverError(detail=f"Failed to save menu: {str(e)}")
    return CreateMenuResponse(name=menu_model.name)


@router.delete(
    "/menu/{name}",
    response_model=DeleteMenuResponse,
    responses={404: {"model": Detail}},
    summary="Delete a menu by its name.",
    operation_id="delete_menu",
)
def deleteMenu(name: str) -> DeleteMenuResponse | NotFoundErrorResponse:
    """
    Delete a menu by its name.

    Args:
        name (str): The name of the menu to be deleted.

    Returns:
        DeleteMenuResponse | NotFoundErrorResponse: The response indicating the success or failure of the deletion.

    Raises:
        None

    """
    existing_menu = MenuModel.find_one(MenuModel.name == name).run()
    if existing_menu is not None:
        existing_menu.delete()
        return DeleteMenuResponse(name=existing_menu.name)
    else:
        logger.warn(f"menu not found: {name}")
        return NotFoundErrorResponse(detail=f"menu not found: {name}")


@router.put(
    "/menu/{name}",
    response_model=UpdateMenuResponse,
    responses={404: {"model": Detail}},
    summary="Update a menu with the given name.",
    operation_id="update_menu",
)
def updateMenu(
    name: str, req: UpdateMenuRequest
) -> UpdateMenuResponse | NotFoundErrorResponse:
    """
    Update a menu with the given name.

    Args:
        id (str): The name of the menu to update.
        req (UpdateMenuRequest): The request object containing the updated menu data.

    Returns:
        Union[UpdateMenuResponse, NotFoundErrorResponse]: The response object indicating the success of the update or an error if the menu is not found.
    """
    existing_menu = MenuModel.find_one(MenuModel.name == name).run()
    if existing_menu:
        existing_menu.name = req.name
        existing_menu.description = req.description
        existing_menu.one_qubit_calib_plan = req.one_qubit_calib_plan
        existing_menu.two_qubit_calib_plan = req.two_qubit_calib_plan
        existing_menu.mode = req.mode
        existing_menu.notify_bool = req.notify_bool
        existing_menu.flow = req.flow
        existing_menu.tags = req.tags
        existing_menu.exp_list = req.exp_list
        existing_menu.save()
        return UpdateMenuResponse(name=existing_menu.name)
    else:
        logger.warn(f"menu not found: {name}")
        return NotFoundErrorResponse(detail=f"menu not found: {name}")


@router.get(
    "/menu/{name}",
    response_model=GetMenuResponse,
    summary="Retrieve a menu by its name.",
    responses={404: {"model": Detail}},
    operation_id="get_menu_by_name",
)
def get_menu_by_name(name: str) -> GetMenuResponse | NotFoundErrorResponse:
    """
    Retrieve a menu by its name.

    Args:
        name (str): The name of the menu.

    Returns:
        GetMenuResponse: The response containing the menu details.

    Raises:
        InternalServerError: If there is an error retrieving the menu.
        NotFoundErrorResponse: If the menu is not found.
    """
    try:
        menu = MenuModel.find_one(MenuModel.name == name).run()
    except Exception as e:
        logger.error(f"Failed to get menu: {e}")
        raise InternalSeverError(detail=f"Failed to get menu: {str(e)}")
    if menu is None:
        return NotFoundErrorResponse(detail=f"menu not found: {name}")
    return GetMenuResponse(
        name=menu.name,
        description=menu.description,
        one_qubit_calib_plan=menu.one_qubit_calib_plan,
        two_qubit_calib_plan=menu.two_qubit_calib_plan,
        mode=menu.mode,
        notify_bool=menu.notify_bool,
        flow=menu.flow,
        exp_list=menu.exp_list,
        tags=menu.tags,
    )
