from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from qdash.client.rest.api_client import ApiClient as RestApiClient
from qdash.client.rest.configuration import Configuration as RestConfiguration
from qdash.client.rest.exceptions import ApiException as RestApiException

if TYPE_CHECKING:
    from collections.abc import Callable

    from qdash.client.rest.api_response import ApiResponse as RestApiResponse
from qdash.client.services.config import QDashConfig
from qdash.client.services.errors import (
    QDashApiError,
    QDashAuthError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
)
from qdash.client.services.exporter_models import NormalizedMetricRecord
from qdash.client.services.models import (
    ChipMetricsResponse,
    ListChipsResponse,
    TimeSeriesData,
)

PACKAGE_NAME = "qdash"
TModel = TypeVar("TModel", bound=BaseModel)


def _resolve_user_agent() -> str:
    try:
        package_version = version(PACKAGE_NAME)
    except PackageNotFoundError:
        package_version = "unknown"
    return f"qdash-client/{package_version}"


class QDashClient:
    """HTTP client for interacting with the QDash API."""

    def __init__(
        self,
        config: QDashConfig | None = None,
        *,
        http_client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.config = config or QDashConfig.from_file()
        self._sleep = sleep_fn or time.sleep
        self._rest_client = RestApiClient(
            RestConfiguration(
                host=self.config.base_url,
                timeout=self.config.timeout_sec,
                verify_tls=self.config.verify_tls,
                proxy=self.config.proxy,
            ),
            http_client=http_client,
        )
        self._default_headers = default_headers or {}

        self._token: str | None = self.config.api_token
        if not self.config.user_agent or self.config.user_agent == "qdash-client/dev":
            self.config.user_agent = _resolve_user_agent()

    def close(self) -> None:
        self._rest_client.close()

    def _validate_model_payload(
        self,
        model_type: type[TModel],
        payload: Any,
    ) -> TModel:
        if isinstance(payload, dict):
            normalized_payload = self._normalize_datetime_fields(payload)
            try:
                return model_type.model_validate(normalized_payload)
            except ValidationError as exc:
                raise QDashValidationError(
                    f"Response payload did not match {model_type.__name__}",
                    payload=payload,
                ) from exc
        raise QDashValidationError(
            f"Response payload did not match {model_type.__name__}",
            payload=payload,
        )

    def _normalize_datetime_fields(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            normalized: dict[str, Any] = {}
            for key, value in payload.items():
                if isinstance(value, str) and key.endswith("_at"):
                    normalized[key] = self._normalize_datetime_string(value)
                else:
                    normalized[key] = self._normalize_datetime_fields(value)
            return normalized
        if isinstance(payload, list):
            return [self._normalize_datetime_fields(item) for item in payload]
        return payload

    def _normalize_datetime_string(self, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if parsed.tzinfo is None:
            return f"{value}+00:00"
        return value

    def _empty_chip_metrics(self) -> ChipMetricsResponse:
        return ChipMetricsResponse(
            chip_id="",
            username="",
            qubit_count=0,
            within_hours=None,
            start_at=None,
            end_at=None,
            qubit_metrics={},
            coupling_metrics={},
        )

    def _coerce_chip_metrics_payload(self, payload: dict[str, Any]) -> ChipMetricsResponse:
        # Keep backward compatibility with looser payloads that are still useful to callers.
        return ChipMetricsResponse.model_construct(
            chip_id=str(payload.get("chip_id") or ""),
            username=str(payload.get("username") or ""),
            qubit_count=int(payload.get("qubit_count", 0) or 0),
            within_hours=(
                int(payload["within_hours"]) if payload.get("within_hours") is not None else None
            ),
            start_at=payload.get("start_at"),
            end_at=payload.get("end_at"),
            qubit_metrics=(
                payload.get("qubit_metrics")
                if isinstance(payload.get("qubit_metrics"), dict)
                else {}
            ),
            coupling_metrics=(
                payload.get("coupling_metrics")
                if isinstance(payload.get("coupling_metrics"), dict)
                else {}
            ),
        )

    def list_chips(self) -> ListChipsResponse:
        response = self._request("GET", "/chips")
        return self._validate_model_payload(
            ListChipsResponse,
            response.data,
        )

    def get_chip_metrics(self, chip_id: str) -> ChipMetricsResponse:
        response = self._request("GET", f"/metrics/chips/{chip_id}/metrics")
        data = response.data
        if isinstance(data, dict):
            normalized_data = self._normalize_datetime_fields(data)
            try:
                return ChipMetricsResponse.model_validate(normalized_data)
            except ValidationError:
                return self._coerce_chip_metrics_payload(normalized_data)
        return self._empty_chip_metrics()

    def get_metrics_config(self) -> dict[str, Any]:
        response = self._request("GET", "/metrics/config")
        data = response.data
        return data if isinstance(data, dict) else {}

    def get_task_results_timeseries(
        self,
        *,
        chip_id: str,
        parameter: str,
        tag: str | None = None,
        qid: str | None = None,
        start_at: str,
        end_at: str,
    ) -> TimeSeriesData:
        params: dict[str, Any] = {
            "chip_id": chip_id,
            "parameter": parameter,
            "start_at": start_at,
            "end_at": end_at,
        }
        if tag:
            params["tag"] = tag
        if qid:
            params["qid"] = qid

        response = self._request("GET", "/task-results/timeseries", params=params)
        return self._validate_model_payload(
            TimeSeriesData,
            response.data,
        )

    async def list_chips_async(self) -> ListChipsResponse:
        """Async variant of list_chips using the same auth/header behavior."""

        response = await self._request_async("/chips")
        return self._validate_model_payload(
            ListChipsResponse,
            response.json(),
        )

    async def get_task_results_timeseries_async(
        self,
        *,
        chip_id: str,
        parameter: str,
        tag: str | None = None,
        qid: str | None = None,
        start_at: str,
        end_at: str,
    ) -> TimeSeriesData:
        """Async variant of get_task_results_timeseries."""

        params: dict[str, Any] = {
            "chip_id": chip_id,
            "parameter": parameter,
            "start_at": start_at,
            "end_at": end_at,
        }
        if tag:
            params["tag"] = tag
        if qid:
            params["qid"] = qid

        response = await self._request_async("/task-results/timeseries", params=params)
        return self._validate_model_payload(
            TimeSeriesData,
            response.json(),
        )

    async def get_metrics_config_async(self) -> dict[str, Any]:
        """Async variant of get_metrics_config."""

        response = await self._request_async("/metrics/config")
        data = response.json()
        return data if isinstance(data, dict) else {}

    def normalize_chip_metrics(
        self, chip_id: str, payload: dict[str, Any]
    ) -> list[NormalizedMetricRecord]:
        records: list[NormalizedMetricRecord] = []

        metrics = payload.get("metrics")
        if isinstance(metrics, list):
            for item in metrics:
                record = self._normalize_row(chip_id, item)
                if record is not None:
                    records.append(record)

        qubit_metrics = payload.get("qubit_metrics")
        if isinstance(qubit_metrics, list):
            for item in qubit_metrics:
                qubit_id = str(item.get("qubit_id") or item.get("entity_id") or "")
                metric_map = item.get("metrics")
                if not qubit_id or not isinstance(metric_map, dict):
                    continue
                for metric_name, metric_payload in metric_map.items():
                    if not isinstance(metric_payload, dict):
                        continue
                    value = metric_payload.get("value")
                    if not isinstance(value, (int, float)):
                        continue
                    observed_at = self._parse_datetime(metric_payload.get("observed_at"))
                    records.append(
                        NormalizedMetricRecord(
                            chip_id=chip_id,
                            entity_type="qubit",
                            entity_id=qubit_id,
                            metric_name=str(metric_name),
                            value=float(value),
                            unit=str(metric_payload.get("unit") or ""),
                            observed_at=observed_at,
                        )
                    )

        coupling_metrics = payload.get("coupling_metrics")
        if isinstance(coupling_metrics, list):
            for item in coupling_metrics:
                record = self._normalize_row(chip_id, item, default_entity_type="coupling")
                if record is not None:
                    records.append(record)

        return records

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> RestApiResponse[Any]:
        attempts = self.config.retry.max_attempts

        for attempt in range(1, attempts + 1):
            headers = self._build_headers()
            try:
                response = self._rest_client.request(
                    method,
                    path,
                    params=params,
                    headers=headers,
                    raise_on_status=False,
                )
            except RestApiException as exc:
                if attempt < attempts:
                    self._sleep(self._retry_delay_for_attempt(attempt))
                    continue
                raise QDashTransportError(str(exc), payload=exc.body) from exc

            if (
                response.status_code == 401
                and self.config.api_token is None
                and self.config.username
            ):
                self._token = None
                if attempt < attempts:
                    self._sleep(self._retry_delay_for_attempt(attempt, response))
                    continue

            if response.status_code < 400:
                return response

            if self._is_retryable_status(response.status_code) and attempt < attempts:
                self._sleep(self._retry_delay_for_attempt(attempt, response))
                continue

            raise self._raise_for_api_response(method, path, response)

        raise QDashTransportError("request exhausted all retries")

    async def _request_async(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        attempts = self.config.retry.max_attempts

        for attempt in range(1, attempts + 1):
            headers = self._build_headers()
            try:
                async with httpx.AsyncClient(
                    base_url=self.config.base_url,
                    timeout=self.config.timeout_sec,
                    verify=self.config.verify_tls,
                    proxy=self.config.proxy,
                ) as client:
                    response = await client.get(path, params=params, headers=headers)
            except httpx.HTTPError as exc:
                if attempt < attempts:
                    await asyncio.sleep(self._retry_delay_for_attempt(attempt))
                    continue
                raise QDashTransportError(str(exc)) from exc

            if (
                response.status_code == 401
                and self.config.api_token is None
                and self.config.username
            ):
                self._token = None
                if attempt < attempts:
                    await asyncio.sleep(self._retry_delay_for_attempt(attempt, response))
                    continue

            if response.status_code < 400:
                return response

            if self._is_retryable_status(response.status_code) and attempt < attempts:
                await asyncio.sleep(self._retry_delay_for_attempt(attempt, response))
                continue

            raise self._raise_for_response(response)

        raise QDashTransportError("request exhausted all retries")

    def _build_headers(self) -> dict[str, str]:
        token = self._get_token()
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": self.config.user_agent,
            "Authorization": f"Bearer {token}",
        }
        if self.config.project_id:
            headers["X-Project-Id"] = self.config.project_id
        if self.config.cf_access_client_id:
            headers["CF-Access-Client-Id"] = self.config.cf_access_client_id
        if self.config.cf_access_client_secret:
            headers["CF-Access-Client-Secret"] = self.config.cf_access_client_secret
        headers.update(self._default_headers)
        return headers

    def _get_token(self) -> str:
        if self._token:
            return self._token
        if self.config.api_token:
            self._token = self.config.api_token
            return self._token
        if not self.config.username:
            raise QDashAuthError("No authentication method configured", status_code=401)

        if not self.config.password_env:
            raise QDashAuthError(
                "password_env is required when using username/password", status_code=401
            )

        import os

        password = os.getenv(self.config.password_env)
        if not password:
            raise QDashAuthError(
                f"Missing password in env var {self.config.password_env}",
                status_code=401,
            )

        try:
            response = self._rest_client.request(
                "POST",
                "/auth/login",
                json={"username": self.config.username, "password": password},
                headers={"Accept": "application/json", "User-Agent": self.config.user_agent},
                raise_on_status=False,
            )
        except RestApiException as exc:
            raise QDashTransportError(str(exc), payload=exc.body) from exc
        if response.status_code >= 400:
            raise self._raise_for_api_response("POST", "/auth/login", response)

        payload = response.data
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise QDashAuthError("Login response did not include access_token", status_code=401)
        self._token = str(token)
        return self._token

    def _is_retryable_status(self, status_code: int) -> bool:
        # Follow OpenAPI-declared responses for the currently supported GET endpoints.
        # They do not define retryable status responses.
        return False

    def _retry_delay_for_attempt(
        self,
        attempt: int,
        response: httpx.Response | RestApiResponse[Any] | None = None,
    ) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass

        base = self.config.retry.base_delay_sec
        max_delay = self.config.retry.max_delay_sec
        delay = min(max_delay, base * (2 ** (attempt - 1)))
        jitter = random.uniform(0.0, delay * 0.1)  # noqa: S311
        return delay + jitter

    def _raise_for_response(self, response: httpx.Response) -> QDashApiError:
        status = response.status_code
        message = self._response_message(response)

        if status == 404:
            return QDashNotFoundError(message, status_code=status)
        if status == 422:
            return QDashValidationError(message, status_code=status)
        return QDashTransportError(message, status_code=status)

    def _raise_for_api_response(
        self,
        method: str,
        path: str,
        response: RestApiResponse[Any],
    ) -> QDashApiError:
        request = httpx.Request(method, f"{self.config.base_url}{path}")
        payload = response.data

        if isinstance(payload, (dict, list)):
            httpx_response = httpx.Response(
                response.status_code,
                request=request,
                json=payload,
                headers=response.headers,
            )
        else:
            httpx_response = httpx.Response(
                response.status_code,
                request=request,
                text="" if payload is None else str(payload),
                headers=response.headers,
            )

        err = self._raise_for_response(httpx_response)
        err.payload = payload
        return err

    def _response_message(self, response: httpx.Response) -> str:
        request = response.request
        endpoint = request.url.path if request is not None else "<unknown>"
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("detail")
                if detail:
                    return f"{response.status_code} {endpoint}: {detail}"
            if isinstance(body, str):
                return f"{response.status_code} {endpoint}: {body}"
        except Exception:  # noqa: S110
            pass
        return f"{response.status_code} {endpoint}"

    def _normalize_row(
        self,
        chip_id: str,
        row: Any,
        *,
        default_entity_type: str = "qubit",
    ) -> NormalizedMetricRecord | None:
        if not isinstance(row, dict):
            return None

        value = row.get("value")
        if not isinstance(value, (int, float)):
            return None

        entity_id = row.get("entity_id") or row.get("qubit_id") or row.get("coupling_id")
        metric_name = row.get("metric_name")
        if not entity_id or not metric_name:
            return None

        return NormalizedMetricRecord(
            chip_id=chip_id,
            entity_type=str(row.get("entity_type") or default_entity_type),
            entity_id=str(entity_id),
            metric_name=str(metric_name),
            value=float(value),
            unit=str(row.get("unit") or ""),
            observed_at=self._parse_datetime(row.get("observed_at")),
        )

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC)
        except ValueError:
            return None
