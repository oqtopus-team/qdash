from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.latest_task_grouped_by_chip_response import LatestTaskGroupedByChipResponse


def _get_kwargs(
    chip_id: str,
    task_name: str,
    recorded_date: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/chip/{chip_id}/task/coupling/{task_name}/history/{recorded_date}".format(
            chip_id=chip_id,
            task_name=task_name,
            recorded_date=recorded_date,
        ),
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[HTTPValidationError, LatestTaskGroupedByChipResponse]]:
    if response.status_code == 200:
        response_200 = LatestTaskGroupedByChipResponse.from_dict(response.json())

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
) -> Response[Union[HTTPValidationError, LatestTaskGroupedByChipResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    chip_id: str,
    task_name: str,
    recorded_date: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[HTTPValidationError, LatestTaskGroupedByChipResponse]]:
    """Fetch historical task results

     Fetch historical task results for a specific date.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    task_name : str
        Name of the task to fetch
    recorded_date : str
        Date to fetch history for (ISO format YYYY-MM-DD)
    current_user : User
        Current authenticated user

    Returns
    -------
    LatestTaskGroupedByChipResponse
        Historical task results for all qubits on the specified date

    Args:
        chip_id (str):
        task_name (str):
        recorded_date (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, LatestTaskGroupedByChipResponse]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
        task_name=task_name,
        recorded_date=recorded_date,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    chip_id: str,
    task_name: str,
    recorded_date: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[HTTPValidationError, LatestTaskGroupedByChipResponse]]:
    """Fetch historical task results

     Fetch historical task results for a specific date.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    task_name : str
        Name of the task to fetch
    recorded_date : str
        Date to fetch history for (ISO format YYYY-MM-DD)
    current_user : User
        Current authenticated user

    Returns
    -------
    LatestTaskGroupedByChipResponse
        Historical task results for all qubits on the specified date

    Args:
        chip_id (str):
        task_name (str):
        recorded_date (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, LatestTaskGroupedByChipResponse]
    """

    return sync_detailed(
        chip_id=chip_id,
        task_name=task_name,
        recorded_date=recorded_date,
        client=client,
    ).parsed


async def asyncio_detailed(
    chip_id: str,
    task_name: str,
    recorded_date: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[HTTPValidationError, LatestTaskGroupedByChipResponse]]:
    """Fetch historical task results

     Fetch historical task results for a specific date.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    task_name : str
        Name of the task to fetch
    recorded_date : str
        Date to fetch history for (ISO format YYYY-MM-DD)
    current_user : User
        Current authenticated user

    Returns
    -------
    LatestTaskGroupedByChipResponse
        Historical task results for all qubits on the specified date

    Args:
        chip_id (str):
        task_name (str):
        recorded_date (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, LatestTaskGroupedByChipResponse]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
        task_name=task_name,
        recorded_date=recorded_date,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    chip_id: str,
    task_name: str,
    recorded_date: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[HTTPValidationError, LatestTaskGroupedByChipResponse]]:
    """Fetch historical task results

     Fetch historical task results for a specific date.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    task_name : str
        Name of the task to fetch
    recorded_date : str
        Date to fetch history for (ISO format YYYY-MM-DD)
    current_user : User
        Current authenticated user

    Returns
    -------
    LatestTaskGroupedByChipResponse
        Historical task results for all qubits on the specified date

    Args:
        chip_id (str):
        task_name (str):
        recorded_date (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, LatestTaskGroupedByChipResponse]
    """

    return (
        await asyncio_detailed(
            chip_id=chip_id,
            task_name=task_name,
            recorded_date=recorded_date,
            client=client,
        )
    ).parsed
