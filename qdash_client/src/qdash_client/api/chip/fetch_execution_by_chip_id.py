from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.execution_response_detail import ExecutionResponseDetail
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    chip_id: str,
    execution_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/api/chip/{chip_id}/execution/{execution_id}",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[ExecutionResponseDetail, HTTPValidationError]]:
    if response.status_code == 200:
        response_200 = ExecutionResponseDetail.from_dict(response.json())

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
) -> Response[Union[ExecutionResponseDetail, HTTPValidationError]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    chip_id: str,
    execution_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[ExecutionResponseDetail, HTTPValidationError]]:
    """Fetch an execution by its ID

     Return the execution detail by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    execution_id : str
        ID of the execution to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ExecutionResponseDetail
        Detailed execution information

    Args:
        chip_id (str):
        execution_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[ExecutionResponseDetail, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
        execution_id=execution_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    chip_id: str,
    execution_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[ExecutionResponseDetail, HTTPValidationError]]:
    """Fetch an execution by its ID

     Return the execution detail by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    execution_id : str
        ID of the execution to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ExecutionResponseDetail
        Detailed execution information

    Args:
        chip_id (str):
        execution_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[ExecutionResponseDetail, HTTPValidationError]
    """

    return sync_detailed(
        chip_id=chip_id,
        execution_id=execution_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    chip_id: str,
    execution_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[ExecutionResponseDetail, HTTPValidationError]]:
    """Fetch an execution by its ID

     Return the execution detail by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    execution_id : str
        ID of the execution to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ExecutionResponseDetail
        Detailed execution information

    Args:
        chip_id (str):
        execution_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[ExecutionResponseDetail, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
        execution_id=execution_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    chip_id: str,
    execution_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[ExecutionResponseDetail, HTTPValidationError]]:
    """Fetch an execution by its ID

     Return the execution detail by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    execution_id : str
        ID of the execution to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ExecutionResponseDetail
        Detailed execution information

    Args:
        chip_id (str):
        execution_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[ExecutionResponseDetail, HTTPValidationError]
    """

    return (
        await asyncio_detailed(
            chip_id=chip_id,
            execution_id=execution_id,
            client=client,
        )
    ).parsed
