from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.detail import Detail
from ...models.http_validation_error import HTTPValidationError
from ...models.update_menu_request import UpdateMenuRequest
from ...models.update_menu_response import UpdateMenuResponse
from ...types import Response


def _get_kwargs(
    name: str,
    *,
    body: UpdateMenuRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": f"/api/menu/{name}",
    }

    _body = body.to_dict()

    _kwargs["json"] = _body
    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Detail, HTTPValidationError, UpdateMenuResponse]]:
    if response.status_code == 200:
        response_200 = UpdateMenuResponse.from_dict(response.json())

        return response_200
    if response.status_code == 404:
        response_404 = Detail.from_dict(response.json())

        return response_404
    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Detail, HTTPValidationError, UpdateMenuResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    name: str,
    *,
    client: Union[AuthenticatedClient, Client],
    body: UpdateMenuRequest,
) -> Response[Union[Detail, HTTPValidationError, UpdateMenuResponse]]:
    """Update a menu with the given name.

     Update a menu with the given name.

    Args:
    ----
        name (str): The name of the menu to update.
        req (UpdateMenuRequest): The request object containing the updated menu data.
        current_user (User): The current authenticated user.

    Returns:
    -------
        Union[UpdateMenuResponse, NotFoundErrorResponse]: The response object indicating the success of
    the update or an error if the menu is not found.

    Args:
        name (str):
        body (UpdateMenuRequest): UpdateMenuRequest is a Pydantic model for updating a menu item.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Detail, HTTPValidationError, UpdateMenuResponse]]
    """

    kwargs = _get_kwargs(
        name=name,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    name: str,
    *,
    client: Union[AuthenticatedClient, Client],
    body: UpdateMenuRequest,
) -> Optional[Union[Detail, HTTPValidationError, UpdateMenuResponse]]:
    """Update a menu with the given name.

     Update a menu with the given name.

    Args:
    ----
        name (str): The name of the menu to update.
        req (UpdateMenuRequest): The request object containing the updated menu data.
        current_user (User): The current authenticated user.

    Returns:
    -------
        Union[UpdateMenuResponse, NotFoundErrorResponse]: The response object indicating the success of
    the update or an error if the menu is not found.

    Args:
        name (str):
        body (UpdateMenuRequest): UpdateMenuRequest is a Pydantic model for updating a menu item.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Detail, HTTPValidationError, UpdateMenuResponse]
    """

    return sync_detailed(
        name=name,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    name: str,
    *,
    client: Union[AuthenticatedClient, Client],
    body: UpdateMenuRequest,
) -> Response[Union[Detail, HTTPValidationError, UpdateMenuResponse]]:
    """Update a menu with the given name.

     Update a menu with the given name.

    Args:
    ----
        name (str): The name of the menu to update.
        req (UpdateMenuRequest): The request object containing the updated menu data.
        current_user (User): The current authenticated user.

    Returns:
    -------
        Union[UpdateMenuResponse, NotFoundErrorResponse]: The response object indicating the success of
    the update or an error if the menu is not found.

    Args:
        name (str):
        body (UpdateMenuRequest): UpdateMenuRequest is a Pydantic model for updating a menu item.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Detail, HTTPValidationError, UpdateMenuResponse]]
    """

    kwargs = _get_kwargs(
        name=name,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    name: str,
    *,
    client: Union[AuthenticatedClient, Client],
    body: UpdateMenuRequest,
) -> Optional[Union[Detail, HTTPValidationError, UpdateMenuResponse]]:
    """Update a menu with the given name.

     Update a menu with the given name.

    Args:
    ----
        name (str): The name of the menu to update.
        req (UpdateMenuRequest): The request object containing the updated menu data.
        current_user (User): The current authenticated user.

    Returns:
    -------
        Union[UpdateMenuResponse, NotFoundErrorResponse]: The response object indicating the success of
    the update or an error if the menu is not found.

    Args:
        name (str):
        body (UpdateMenuRequest): UpdateMenuRequest is a Pydantic model for updating a menu item.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Detail, HTTPValidationError, UpdateMenuResponse]
    """

    return (
        await asyncio_detailed(
            name=name,
            client=client,
            body=body,
        )
    ).parsed
