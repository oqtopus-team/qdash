from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response
from ... import errors

from ...models.chip_dates_response import ChipDatesResponse
from ...models.http_validation_error import HTTPValidationError


def _get_kwargs(
    chip_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/chip/{chip_id}/dates".format(
            chip_id=chip_id,
        ),
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[ChipDatesResponse, HTTPValidationError]]:
    if response.status_code == 200:
        response_200 = ChipDatesResponse.from_dict(response.json())

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
) -> Response[Union[ChipDatesResponse, HTTPValidationError]]:
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
) -> Response[Union[ChipDatesResponse, HTTPValidationError]]:
    """Fetch available dates for a chip

     Fetch available dates for a chip from execution counter.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    list[str]
        List of available dates in ISO format

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[ChipDatesResponse, HTTPValidationError]]
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
) -> Optional[Union[ChipDatesResponse, HTTPValidationError]]:
    """Fetch available dates for a chip

     Fetch available dates for a chip from execution counter.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    list[str]
        List of available dates in ISO format

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[ChipDatesResponse, HTTPValidationError]
    """

    return sync_detailed(
        chip_id=chip_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    chip_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[ChipDatesResponse, HTTPValidationError]]:
    """Fetch available dates for a chip

     Fetch available dates for a chip from execution counter.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    list[str]
        List of available dates in ISO format

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[ChipDatesResponse, HTTPValidationError]]
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
) -> Optional[Union[ChipDatesResponse, HTTPValidationError]]:
    """Fetch available dates for a chip

     Fetch available dates for a chip from execution counter.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    list[str]
        List of available dates in ISO format

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[ChipDatesResponse, HTTPValidationError]
    """

    return (
        await asyncio_detailed(
            chip_id=chip_id,
            client=client,
        )
    ).parsed
