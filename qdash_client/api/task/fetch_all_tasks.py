from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.list_task_response import ListTaskResponse
from ...types import Unset


def _get_kwargs(
    *,
    backend: Union[None, Unset, str] = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_backend: Union[None, Unset, str]
    if isinstance(backend, Unset):
        json_backend = UNSET
    else:
        json_backend = backend
    params["backend"] = json_backend

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/tasks",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[HTTPValidationError, ListTaskResponse]]:
    if response.status_code == 200:
        response_200 = ListTaskResponse.from_dict(response.json())

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
) -> Response[Union[HTTPValidationError, ListTaskResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    backend: Union[None, Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, ListTaskResponse]]:
    """Fetch all tasks

     Fetch all tasks.

    Args:
    ----
        current_user (User): The current user.
        backend (Optional[str]): Optional backend name to filter tasks by.

    Returns:
    -------
        list[TaskResponse]: The list of tasks.

    Args:
        backend (Union[None, Unset, str]): Optional backend name to filter tasks by

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, ListTaskResponse]]
    """

    kwargs = _get_kwargs(
        backend=backend,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
    backend: Union[None, Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, ListTaskResponse]]:
    """Fetch all tasks

     Fetch all tasks.

    Args:
    ----
        current_user (User): The current user.
        backend (Optional[str]): Optional backend name to filter tasks by.

    Returns:
    -------
        list[TaskResponse]: The list of tasks.

    Args:
        backend (Union[None, Unset, str]): Optional backend name to filter tasks by

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, ListTaskResponse]
    """

    return sync_detailed(
        client=client,
        backend=backend,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    backend: Union[None, Unset, str] = UNSET,
) -> Response[Union[HTTPValidationError, ListTaskResponse]]:
    """Fetch all tasks

     Fetch all tasks.

    Args:
    ----
        current_user (User): The current user.
        backend (Optional[str]): Optional backend name to filter tasks by.

    Returns:
    -------
        list[TaskResponse]: The list of tasks.

    Args:
        backend (Union[None, Unset, str]): Optional backend name to filter tasks by

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, ListTaskResponse]]
    """

    kwargs = _get_kwargs(
        backend=backend,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    backend: Union[None, Unset, str] = UNSET,
) -> Optional[Union[HTTPValidationError, ListTaskResponse]]:
    """Fetch all tasks

     Fetch all tasks.

    Args:
    ----
        current_user (User): The current user.
        backend (Optional[str]): Optional backend name to filter tasks by.

    Returns:
    -------
        list[TaskResponse]: The list of tasks.

    Args:
        backend (Union[None, Unset, str]): Optional backend name to filter tasks by

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, ListTaskResponse]
    """

    return (
        await asyncio_detailed(
            client=client,
            backend=backend,
        )
    ).parsed
