from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.chip_response import ChipResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    chip_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/api/chip/{chip_id}",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[ChipResponse, HTTPValidationError]]:
    if response.status_code == 200:
        response_200 = ChipResponse.from_dict(response.json())

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
) -> Response[Union[ChipResponse, HTTPValidationError]]:
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
) -> Response[Union[ChipResponse, HTTPValidationError]]:
    """Fetch a chip

     Fetch a chip by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ChipResponse
        Chip information

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[ChipResponse, HTTPValidationError]]
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
) -> Optional[Union[ChipResponse, HTTPValidationError]]:
    """Fetch a chip

     Fetch a chip by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ChipResponse
        Chip information

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[ChipResponse, HTTPValidationError]
    """

    return sync_detailed(
        chip_id=chip_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    chip_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[ChipResponse, HTTPValidationError]]:
    """Fetch a chip

     Fetch a chip by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ChipResponse
        Chip information

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[ChipResponse, HTTPValidationError]]
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
) -> Optional[Union[ChipResponse, HTTPValidationError]]:
    """Fetch a chip

     Fetch a chip by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ChipResponse
        Chip information

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[ChipResponse, HTTPValidationError]
    """

    return (
        await asyncio_detailed(
            chip_id=chip_id,
            client=client,
        )
    ).parsed
