from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.list_mux_response import ListMuxResponse
from ...types import Response


def _get_kwargs(
    chip_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/api/chip/{chip_id}/mux",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[HTTPValidationError, ListMuxResponse]]:
    if response.status_code == 200:
        response_200 = ListMuxResponse.from_dict(response.json())

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[HTTPValidationError, ListMuxResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    chip_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[HTTPValidationError, ListMuxResponse]]:
    """Fetch the multiplexers

     Fetch the multiplexers.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    ListMuxResponse
        Multiplexdetails

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, ListMuxResponse]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    chip_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[HTTPValidationError, ListMuxResponse]]:
    """Fetch the multiplexers

     Fetch the multiplexers.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    ListMuxResponse
        Multiplexdetails

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, ListMuxResponse]
    """

    return sync_detailed(
        chip_id=chip_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    chip_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[HTTPValidationError, ListMuxResponse]]:
    """Fetch the multiplexers

     Fetch the multiplexers.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    ListMuxResponse
        Multiplexdetails

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, ListMuxResponse]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    chip_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[HTTPValidationError, ListMuxResponse]]:
    """Fetch the multiplexers

     Fetch the multiplexers.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    ListMuxResponse
        Multiplexdetails

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, ListMuxResponse]
    """

    return (
        await asyncio_detailed(
            chip_id=chip_id,
            client=client,
        )
    ).parsed
