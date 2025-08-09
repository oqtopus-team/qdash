from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.create_menu_request import CreateMenuRequest
from ...models.create_menu_response import CreateMenuResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: CreateMenuRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/menu",
    }

    _body = body.to_dict()

    _kwargs["json"] = _body
    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[CreateMenuResponse, HTTPValidationError]]:
    if response.status_code == 200:
        response_200 = CreateMenuResponse.from_dict(response.json())

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
) -> Response[Union[CreateMenuResponse, HTTPValidationError]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    body: CreateMenuRequest,
) -> Response[Union[CreateMenuResponse, HTTPValidationError]]:
    """Create a new menu item.

     Create a new menu item.

    Args:
    ----
        request (CreateMenuRequest): The request object containing the menu item details.
        current_user (User): The current authenticated user.

    Returns:
    -------
        CreateMenuResponse: The response object containing the name of the created menu item.

    Args:
        body (CreateMenuRequest): CreateMenuRequest is a Pydantic model for creating a menu item.
            Example: {'backend': 'qubex', 'batch_mode': False, 'description': 'This is a sample menu
            item.', 'name': 'CheckOneQubit', 'notify_bool': False, 'qids': [['28', '29']], 'tags':
            ['debug'], 'tasks': ['CheckStatus', 'DumpBox', 'CheckNoise', 'CheckRabi',
            'CreateHPIPulse', 'CheckHPIPulse', 'CreatePIPulse', 'CheckPIPulse', 'CheckT1',
            'CheckT2Echo'], 'username': 'admin'}.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[CreateMenuResponse, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
    body: CreateMenuRequest,
) -> Optional[Union[CreateMenuResponse, HTTPValidationError]]:
    """Create a new menu item.

     Create a new menu item.

    Args:
    ----
        request (CreateMenuRequest): The request object containing the menu item details.
        current_user (User): The current authenticated user.

    Returns:
    -------
        CreateMenuResponse: The response object containing the name of the created menu item.

    Args:
        body (CreateMenuRequest): CreateMenuRequest is a Pydantic model for creating a menu item.
            Example: {'backend': 'qubex', 'batch_mode': False, 'description': 'This is a sample menu
            item.', 'name': 'CheckOneQubit', 'notify_bool': False, 'qids': [['28', '29']], 'tags':
            ['debug'], 'tasks': ['CheckStatus', 'DumpBox', 'CheckNoise', 'CheckRabi',
            'CreateHPIPulse', 'CheckHPIPulse', 'CreatePIPulse', 'CheckPIPulse', 'CheckT1',
            'CheckT2Echo'], 'username': 'admin'}.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[CreateMenuResponse, HTTPValidationError]
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    body: CreateMenuRequest,
) -> Response[Union[CreateMenuResponse, HTTPValidationError]]:
    """Create a new menu item.

     Create a new menu item.

    Args:
    ----
        request (CreateMenuRequest): The request object containing the menu item details.
        current_user (User): The current authenticated user.

    Returns:
    -------
        CreateMenuResponse: The response object containing the name of the created menu item.

    Args:
        body (CreateMenuRequest): CreateMenuRequest is a Pydantic model for creating a menu item.
            Example: {'backend': 'qubex', 'batch_mode': False, 'description': 'This is a sample menu
            item.', 'name': 'CheckOneQubit', 'notify_bool': False, 'qids': [['28', '29']], 'tags':
            ['debug'], 'tasks': ['CheckStatus', 'DumpBox', 'CheckNoise', 'CheckRabi',
            'CreateHPIPulse', 'CheckHPIPulse', 'CreatePIPulse', 'CheckPIPulse', 'CheckT1',
            'CheckT2Echo'], 'username': 'admin'}.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[CreateMenuResponse, HTTPValidationError]]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    body: CreateMenuRequest,
) -> Optional[Union[CreateMenuResponse, HTTPValidationError]]:
    """Create a new menu item.

     Create a new menu item.

    Args:
    ----
        request (CreateMenuRequest): The request object containing the menu item details.
        current_user (User): The current authenticated user.

    Returns:
    -------
        CreateMenuResponse: The response object containing the name of the created menu item.

    Args:
        body (CreateMenuRequest): CreateMenuRequest is a Pydantic model for creating a menu item.
            Example: {'backend': 'qubex', 'batch_mode': False, 'description': 'This is a sample menu
            item.', 'name': 'CheckOneQubit', 'notify_bool': False, 'qids': [['28', '29']], 'tags':
            ['debug'], 'tasks': ['CheckStatus', 'DumpBox', 'CheckNoise', 'CheckRabi',
            'CreateHPIPulse', 'CheckHPIPulse', 'CreatePIPulse', 'CheckPIPulse', 'CheckT1',
            'CheckT2Echo'], 'username': 'admin'}.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[CreateMenuResponse, HTTPValidationError]
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
