from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.time_series_data import TimeSeriesData
from ...types import UNSET, Response


def _get_kwargs(
    chip_id: str,
    parameter: str,
    *,
    tag: str,
    start_at: str,
    end_at: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["tag"] = tag

    params["start_at"] = start_at

    params["end_at"] = end_at

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/api/chip/{chip_id}/parameter/{parameter}",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[HTTPValidationError, TimeSeriesData]]:
    if response.status_code == 200:
        response_200 = TimeSeriesData.from_dict(response.json())

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
) -> Response[Union[HTTPValidationError, TimeSeriesData]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    chip_id: str,
    parameter: str,
    *,
    client: Union[AuthenticatedClient, Client],
    tag: str,
    start_at: str,
    end_at: str,
) -> Response[Union[HTTPValidationError, TimeSeriesData]]:
    """Fetch the timeseries task result by tag and parameter for all qids

     Fetch the timeseries task result by tag and parameter for all qids.

    Returns
    -------
        TimeSeriesData: Time series data for all qids.

    Args:
        chip_id (str):
        parameter (str):
        tag (str):
        start_at (str):
        end_at (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, TimeSeriesData]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
        parameter=parameter,
        tag=tag,
        start_at=start_at,
        end_at=end_at,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    chip_id: str,
    parameter: str,
    *,
    client: Union[AuthenticatedClient, Client],
    tag: str,
    start_at: str,
    end_at: str,
) -> Optional[Union[HTTPValidationError, TimeSeriesData]]:
    """Fetch the timeseries task result by tag and parameter for all qids

     Fetch the timeseries task result by tag and parameter for all qids.

    Returns
    -------
        TimeSeriesData: Time series data for all qids.

    Args:
        chip_id (str):
        parameter (str):
        tag (str):
        start_at (str):
        end_at (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, TimeSeriesData]
    """

    return sync_detailed(
        chip_id=chip_id,
        parameter=parameter,
        client=client,
        tag=tag,
        start_at=start_at,
        end_at=end_at,
    ).parsed


async def asyncio_detailed(
    chip_id: str,
    parameter: str,
    *,
    client: Union[AuthenticatedClient, Client],
    tag: str,
    start_at: str,
    end_at: str,
) -> Response[Union[HTTPValidationError, TimeSeriesData]]:
    """Fetch the timeseries task result by tag and parameter for all qids

     Fetch the timeseries task result by tag and parameter for all qids.

    Returns
    -------
        TimeSeriesData: Time series data for all qids.

    Args:
        chip_id (str):
        parameter (str):
        tag (str):
        start_at (str):
        end_at (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[HTTPValidationError, TimeSeriesData]]
    """

    kwargs = _get_kwargs(
        chip_id=chip_id,
        parameter=parameter,
        tag=tag,
        start_at=start_at,
        end_at=end_at,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    chip_id: str,
    parameter: str,
    *,
    client: Union[AuthenticatedClient, Client],
    tag: str,
    start_at: str,
    end_at: str,
) -> Optional[Union[HTTPValidationError, TimeSeriesData]]:
    """Fetch the timeseries task result by tag and parameter for all qids

     Fetch the timeseries task result by tag and parameter for all qids.

    Returns
    -------
        TimeSeriesData: Time series data for all qids.

    Args:
        chip_id (str):
        parameter (str):
        tag (str):
        start_at (str):
        end_at (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[HTTPValidationError, TimeSeriesData]
    """

    return (
        await asyncio_detailed(
            chip_id=chip_id,
            parameter=parameter,
            client=client,
            tag=tag,
            start_at=start_at,
            end_at=end_at,
        )
    ).parsed
