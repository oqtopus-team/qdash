from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response
from ... import errors

from ...models.detail import Detail
from ...models.list_menu_response import ListMenuResponse


def _get_kwargs() -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/menu/preset",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Detail, ListMenuResponse]]:
    if response.status_code == 200:
        response_200 = ListMenuResponse.from_dict(response.json())

        return response_200
    if response.status_code == 404:
        response_404 = Detail.from_dict(response.json())

        return response_404
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Detail, ListMenuResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Detail, ListMenuResponse]]:
    """Retrieve a list of preset menu items.

     Retrieve a list of preset menu items.

    Returns
    -------
        ListMenuResponse: A response containing the list of preset menu items.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Detail, ListMenuResponse]]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Detail, ListMenuResponse]]:
    """Retrieve a list of preset menu items.

     Retrieve a list of preset menu items.

    Returns
    -------
        ListMenuResponse: A response containing the list of preset menu items.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Detail, ListMenuResponse]
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Detail, ListMenuResponse]]:
    """Retrieve a list of preset menu items.

     Retrieve a list of preset menu items.

    Returns
    -------
        ListMenuResponse: A response containing the list of preset menu items.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Detail, ListMenuResponse]]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Detail, ListMenuResponse]]:
    """Retrieve a list of preset menu items.

     Retrieve a list of preset menu items.

    Returns
    -------
        ListMenuResponse: A response containing the list of preset menu items.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Detail, ListMenuResponse]
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
