from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from qdash.client.rest.api_response import ApiResponse
from qdash.client.rest.exceptions import ApiException

if TYPE_CHECKING:
    from qdash.client.rest.configuration import Configuration


class ApiClient:
    """Small synchronous REST client used by service layer."""

    def __init__(
        self,
        configuration: Configuration,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.configuration = configuration
        self._client = http_client or httpx.Client(
            base_url=configuration.host,
            timeout=configuration.timeout,
            verify=configuration.verify_tls,
            proxy=configuration.proxy,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        raise_on_status: bool = False,
    ) -> ApiResponse[Any]:
        try:
            response = self._client.request(
                method,
                path,
                headers=headers,
                params=params,
                json=json,
            )
        except httpx.HTTPError as exc:
            raise ApiException(None, str(exc)) from exc

        try:
            payload = response.json()
        except Exception:
            payload = response.text

        if raise_on_status and response.status_code >= 400:
            raise ApiException(response.status_code, response.reason_phrase, payload)

        return ApiResponse(
            status_code=response.status_code,
            data=payload,
            headers=dict(response.headers),
        )

    def close(self) -> None:
        self._client.close()
