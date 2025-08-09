from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.mux_detail_response import MuxDetailResponse
from ...types import Response


def _get_kwargs(
    chip_id: str,
    mux_id: int,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/api/chip/{chip_id}/mux/{mux_id}",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[HTTPValidationError, MuxDetailResponse]]:
    if response.status_code == 200:
        response_200 = MuxDetailResponse.from_dict(response.json())

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
) -> Response[Union[HTTPValidationError, MuxDetailResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    chip_id: str,
    mux_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[HTTPValidationError, MuxDetailResponse]]:
    """Fetch the multiplexer details

     Fetch the multiplexer details.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    mux_id : int
        ID of the multiplexer
    current_user : User
        Current authenticated user

    Returns
    -------
    MuxDetailResponse
        Multiplexer details

    Args:
        chip_id (str):
        mux_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, MuxDetailResponse]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
        mux_id=mux_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    chip_id: str,
    mux_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[HTTPValidationError, MuxDetailResponse]]:
    """Fetch the multiplexer details

     Fetch the multiplexer details.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    mux_id : int
        ID of the multiplexer
    current_user : User
        Current authenticated user

    Returns
    -------
    MuxDetailResponse
        Multiplexer details

    Args:
        chip_id (str):
        mux_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, MuxDetailResponse]
    """

    return sync_detailed(
        chip_id=chip_id,
        mux_id=mux_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    chip_id: str,
    mux_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[HTTPValidationError, MuxDetailResponse]]:
    """Fetch the multiplexer details

     Fetch the multiplexer details.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    mux_id : int
        ID of the multiplexer
    current_user : User
        Current authenticated user

    Returns
    -------
    MuxDetailResponse
        Multiplexer details

    Args:
        chip_id (str):
        mux_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, MuxDetailResponse]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
        mux_id=mux_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    chip_id: str,
    mux_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[HTTPValidationError, MuxDetailResponse]]:
    """Fetch the multiplexer details

     Fetch the multiplexer details.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    mux_id : int
        ID of the multiplexer
    current_user : User
        Current authenticated user

    Returns
    -------
    MuxDetailResponse
        Multiplexer details

    Args:
        chip_id (str):
        mux_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, MuxDetailResponse]
    """

    return (
        await asyncio_detailed(
            chip_id=chip_id,
            mux_id=mux_id,
            client=client,
        )
    ).parsed
