from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response
from ... import errors

from ...models.detail import Detail
from ...models.get_menu_response import GetMenuResponse
from ...models.http_validation_error import HTTPValidationError


def _get_kwargs(
    name: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/menu/{name}".format(
            name=name,
        ),
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Detail, GetMenuResponse, HTTPValidationError]]:
    if response.status_code == 200:
        response_200 = GetMenuResponse.from_dict(response.json())

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
) -> Response[Union[Detail, GetMenuResponse, HTTPValidationError]]:
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
) -> Response[Union[Detail, GetMenuResponse, HTTPValidationError]]:
    """Retrieve a menu by its name.

     Retrieve a menu by its name.

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

    Args:
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Detail, GetMenuResponse, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        name=name,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    name: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Detail, GetMenuResponse, HTTPValidationError]]:
    """Retrieve a menu by its name.

     Retrieve a menu by its name.

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

    Args:
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Detail, GetMenuResponse, HTTPValidationError]
    """

    return sync_detailed(
        name=name,
        client=client,
    ).parsed


async def asyncio_detailed(
    name: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Detail, GetMenuResponse, HTTPValidationError]]:
    """Retrieve a menu by its name.

     Retrieve a menu by its name.

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

    Args:
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Detail, GetMenuResponse, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        name=name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    name: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Detail, GetMenuResponse, HTTPValidationError]]:
    """Retrieve a menu by its name.

     Retrieve a menu by its name.

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

    Args:
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Detail, GetMenuResponse, HTTPValidationError]
    """

    return (
        await asyncio_detailed(
            name=name,
            client=client,
        )
    ).parsed
