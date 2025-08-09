from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response
from ... import errors

from ...models.auth_logout_response_auth_logout import AuthLogoutResponseAuthLogout


def _get_kwargs() -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/auth/logout",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, AuthLogoutResponseAuthLogout]]:
    if response.status_code == 200:
        response_200 = AuthLogoutResponseAuthLogout.from_dict(response.json())

        return response_200
    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Any, AuthLogoutResponseAuthLogout]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Any, AuthLogoutResponseAuthLogout]]:
    """Logout

     Logout endpoint.

    This endpoint doesn't need to do anything on the backend since the username is managed client-side.
    The client will remove the username from cookies.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, AuthLogoutResponseAuthLogout]]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Any, AuthLogoutResponseAuthLogout]]:
    """Logout

     Logout endpoint.

    This endpoint doesn't need to do anything on the backend since the username is managed client-side.
    The client will remove the username from cookies.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, AuthLogoutResponseAuthLogout]
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Any, AuthLogoutResponseAuthLogout]]:
    """Logout

     Logout endpoint.

    This endpoint doesn't need to do anything on the backend since the username is managed client-side.
    The client will remove the username from cookies.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, AuthLogoutResponseAuthLogout]]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Any, AuthLogoutResponseAuthLogout]]:
    """Logout

     Logout endpoint.

    This endpoint doesn't need to do anything on the backend since the username is managed client-side.
    The client will remove the username from cookies.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, AuthLogoutResponseAuthLogout]
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
