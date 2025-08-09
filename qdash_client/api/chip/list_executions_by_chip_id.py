from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response
from ... import errors

from ...models.execution_response_summary import ExecutionResponseSummary
from ...models.http_validation_error import HTTPValidationError


def _get_kwargs(
    chip_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/chip/{chip_id}/execution".format(
            chip_id=chip_id,
        ),
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[HTTPValidationError, list["ExecutionResponseSummary"]]]:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = ExecutionResponseSummary.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[Union[HTTPValidationError, list["ExecutionResponseSummary"]]]:
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
) -> Response[Union[HTTPValidationError, list["ExecutionResponseSummary"]]]:
    """Fetch executions

     Fetch all executions for a given chip.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch executions for
    current_user : str
        Current user ID from authentication

    Returns
    -------
    list[ExecutionResponseSummary]
        List of executions for the chip

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, list['ExecutionResponseSummary']]]
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
) -> Optional[Union[HTTPValidationError, list["ExecutionResponseSummary"]]]:
    """Fetch executions

     Fetch all executions for a given chip.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch executions for
    current_user : str
        Current user ID from authentication

    Returns
    -------
    list[ExecutionResponseSummary]
        List of executions for the chip

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, list['ExecutionResponseSummary']]
    """

    return sync_detailed(
        chip_id=chip_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    chip_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[HTTPValidationError, list["ExecutionResponseSummary"]]]:
    """Fetch executions

     Fetch all executions for a given chip.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch executions for
    current_user : str
        Current user ID from authentication

    Returns
    -------
    list[ExecutionResponseSummary]
        List of executions for the chip

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, list['ExecutionResponseSummary']]]
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
) -> Optional[Union[HTTPValidationError, list["ExecutionResponseSummary"]]]:
    """Fetch executions

     Fetch all executions for a given chip.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch executions for
    current_user : str
        Current user ID from authentication

    Returns
    -------
    list[ExecutionResponseSummary]
        List of executions for the chip

    Args:
        chip_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, list['ExecutionResponseSummary']]
    """

    return (
        await asyncio_detailed(
            chip_id=chip_id,
            client=client,
        )
    ).parsed
