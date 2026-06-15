from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from pathlib import Path
import pytest

from qdash.client import (
    ChipResponse,
    ListChipsResponse,
    QDashClient,
    QDashConfig,
    QDashConfigError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
    TimeSeriesData,
)


def _build_config(**overrides: object) -> QDashConfig:
    base = {
        "base_url": "http://qdash.local",
        "username": "tester",
        "password_env": "QDASH_PASSWORD",
        "timeout_sec": 1.0,
        "max_workers": 2,
        "retry": {
            "max_attempts": 3,
            "base_delay_sec": 0.01,
            "max_delay_sec": 0.05,
        },
    }
    base.update(overrides)
    return QDashConfig.model_validate(base)


def _build_client(
    handler: httpx.MockTransport,
    *,
    max_attempts: int = 3,
    api_token: str | None = None,
) -> QDashClient:
    config = _build_config(
        api_token=api_token,
        retry={"max_attempts": max_attempts, "base_delay_sec": 0.01, "max_delay_sec": 0.05},
    )
    http_client = httpx.Client(
        base_url=config.base_url,
        transport=handler,
        timeout=config.timeout_sec,
        verify=config.verify_tls,
    )
    return QDashClient(config, http_client=http_client, sleep_fn=lambda _sec: None)


def test_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_BASE_URL", "http://env.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "env-token")
    monkeypatch.setenv("QDASH_PROJECT_ID", "project-1")
    monkeypatch.setenv("QDASH_CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("QDASH_CF_ACCESS_CLIENT_SECRET", "cf-secret")
    monkeypatch.setenv("QDASH_RETRY_MAX_ATTEMPTS", "5")

    config = QDashConfig.from_env()

    assert config.base_url == "http://env.local"
    assert config.api_token == "env-token"  # noqa: S105
    assert config.project_id == "project-1"
    assert config.cf_access_client_id == "cf-id"
    assert config.cf_access_client_secret == "cf-secret"  # noqa: S105
    assert config.retry.max_attempts == 5


def test_config_from_file_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "xdg" / "qdash"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.ini"
    config_file.write_text(
        """
[default]
base_url = http://file.local/
username = file-user
password_env = QDASH_PASSWORD
retry_max_attempts = 4
""".strip()
    )

    monkeypatch.delenv("QDASH_BASE_URL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    config = QDashConfig.from_file()

    assert config.base_url == "http://file.local"
    assert config.username == "file-user"
    assert config.retry.max_attempts == 4


def test_config_from_file_default_home_path_expands_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / ".config" / "qdash"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.ini"
    config_file.write_text(
        """
[default]
base_url = http://home.local/
api_token = file-token
""".strip()
    )

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    config = QDashConfig.from_file()

    assert config.base_url == "http://home.local"
    assert config.api_token == "file-token"  # noqa: S105


def test_config_save_writes_selected_section_and_preserves_others(tmp_path: Path) -> None:
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[local]
base_url = http://local.example
api_token = local-token
""".strip()
    )
    config = QDashConfig(
        base_url="https://prod.example/api",
        api_token="prod-token",
        project_id="project-1",
        cf_access_client_id="cf-id",
        cf_access_client_secret="cf-secret",
        timeout_sec=12,
    )

    saved_path = config.save(profile="prod", path=config_file)
    loaded = QDashConfig.from_file(profile="prod", path=config_file)
    local = QDashConfig.from_file(profile="local", path=config_file)

    assert saved_path == config_file
    assert loaded.base_url == "https://prod.example/api"
    assert loaded.api_token == "prod-token"  # noqa: S105
    assert loaded.project_id == "project-1"
    assert loaded.cf_access_client_id == "cf-id"
    assert loaded.cf_access_client_secret == "cf-secret"  # noqa: S105
    assert loaded.timeout_sec == 12
    assert local.base_url == "http://local.example"


def test_config_save_uses_default_path_and_restricts_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = QDashConfig(base_url="https://default.example/api", api_token="token")

    saved_path = config.save()
    loaded = QDashConfig.from_file()

    assert saved_path == tmp_path / "xdg" / "qdash" / "config.ini"
    assert loaded.base_url == "https://default.example/api"
    assert loaded.api_token == "token"  # noqa: S105
    assert saved_path.stat().st_mode & 0o777 == 0o600


def test_config_from_env_missing_base_url_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QDASH_BASE_URL", raising=False)

    with pytest.raises(QDashConfigError):
        QDashConfig.from_env()


def test_token_cache_and_401_reauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_PASSWORD", "secret")

    login_count = 0
    chips_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_count, chips_count
        if request.method == "POST" and request.url.path == "/auth/login":
            login_count += 1
            token = "token-1" if login_count == 1 else "token-2"
            return httpx.Response(200, json={"access_token": token})

        if request.method == "GET" and request.url.path == "/chips":
            chips_count += 1
            auth = request.headers.get("Authorization")
            if chips_count == 1:
                assert auth == "Bearer token-1"
                return httpx.Response(401, json={"detail": "expired"})
            assert auth == "Bearer token-2"
            return httpx.Response(200, json={"chips": [{"chip_id": "chip-a"}], "total": 1})

        return httpx.Response(500, json={"detail": "unexpected"})

    client = _build_client(httpx.MockTransport(handler))
    try:
        chips = client.list_chips()
        assert isinstance(chips, ListChipsResponse)
        assert [chip.chip_id for chip in chips.chips] == ["chip-a"]
        assert login_count == 2
        assert chips_count == 2
    finally:
        client.close()


def test_login_network_error_maps_to_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_PASSWORD", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/auth/login":
            raise httpx.ConnectError("network down", request=request)
        return httpx.Response(500, json={"detail": "unexpected"})

    client = _build_client(httpx.MockTransport(handler))
    try:
        with pytest.raises(QDashTransportError):
            client.list_chips()
    finally:
        client.close()


def test_get_metrics_config_returns_object() -> None:
    payload = {
        "qubit_metrics": {"t1": {"title": "T1"}},
        "coupling_metrics": {"cz_fidelity": {"title": "CZ"}},
        "color_scale": {"colors": ["#000", "#fff"]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/metrics/config":
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        config = client.get_metrics_config()
        assert config == payload
    finally:
        client.close()


def test_get_chip_metrics_returns_object() -> None:
    payload = {
        "chip_id": "chip-a",
        "username": "operator",
        "qubit_count": 64,
        "within_hours": 24,
        "start_at": "2026-01-01T00:00:00Z",
        "end_at": "2026-01-02T00:00:00Z",
        "qubit_metrics": {"t1": {"title": "T1"}},
        "coupling_metrics": {"cz_fidelity": {"title": "CZ"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/metrics/chips/chip-a/metrics":
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        metrics = client.get_chip_metrics("chip-a")
        assert metrics.chip_id == "chip-a"
        assert metrics.username == "operator"
        assert metrics.qubit_count == 64
        assert "t1" in metrics.qubit_metrics
        assert "cz_fidelity" in metrics.coupling_metrics
    finally:
        client.close()


def test_list_chips_accepts_naive_installed_at() -> None:
    payload = {
        "chips": [
            {
                "chip_id": "chip-a",
                "size": 64,
                "qubit_count": 64,
                "coupling_count": 0,
                "activity_status": "active",
                "installed_at": "2025-07-23T08:57:49.799000",
            }
        ],
        "total": 1,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/chips":
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        chips = client.list_chips()
        assert chips.total == 1
        assert chips.chips[0].chip_id == "chip-a"
    finally:
        client.close()


def test_get_default_chip_prefers_first_active_chip() -> None:
    payload = {
        "chips": [
            {
                "chip_id": "chip-inactive-latest",
                "activity_status": "inactive",
                "installed_at": "2026-01-03T00:00:00Z",
            },
            {
                "chip_id": "chip-active-old",
                "activity_status": "active",
                "installed_at": "2026-01-01T00:00:00Z",
            },
            {
                "chip_id": "chip-active-latest",
                "activity_status": "active",
                "installed_at": "2026-01-02T00:00:00Z",
            },
        ],
        "total": 3,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/chips":
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        chip = client.get_default_chip()
        assert isinstance(chip, ChipResponse)
        assert chip.chip_id == "chip-active-old"
        assert client.get_default_chip_id() == "chip-active-old"
    finally:
        client.close()


def test_get_default_chip_falls_back_to_latest_chip() -> None:
    payload = {
        "chips": [
            {
                "chip_id": "chip-old",
                "activity_status": "inactive",
                "installed_at": "2026-01-01T00:00:00Z",
            },
            {
                "chip_id": "chip-latest",
                "activity_status": "inactive",
                "installed_at": "2026-01-02T00:00:00Z",
            },
        ],
        "total": 2,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/chips":
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        assert client.get_default_chip().chip_id == "chip-latest"
    finally:
        client.close()


def test_get_default_chip_does_not_sort_active_chips_by_installed_at() -> None:
    payload = {
        "chips": [
            {"chip_id": "chip-undated", "activity_status": "active"},
            {
                "chip_id": "chip-dated",
                "activity_status": "active",
                "installed_at": "2026-01-01T00:00:00Z",
            },
        ],
        "total": 2,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/chips":
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        assert client.get_default_chip().chip_id == "chip-undated"
    finally:
        client.close()


def test_get_default_chip_raises_not_found_for_empty_chip_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/chips":
            return httpx.Response(200, json={"chips": [], "total": 0})
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        with pytest.raises(QDashNotFoundError):
            client.get_default_chip()
    finally:
        client.close()


def test_list_chips_invalid_payload_raises_validation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/chips":
            return httpx.Response(200, json={"items": []})
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        with pytest.raises(QDashValidationError) as exc_info:
            client.list_chips()
        assert exc_info.value.payload == {"items": []}
    finally:
        client.close()


def test_get_chip_metrics_404_maps_to_not_found_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/metrics/chips/chip-a/metrics":
            return httpx.Response(404, json={"detail": "missing"})
        return httpx.Response(500, json={"detail": "unexpected"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        with pytest.raises(QDashNotFoundError):
            client.get_chip_metrics("chip-a")
    finally:
        client.close()


def test_get_chip_metrics_422_maps_to_validation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/metrics/chips/chip-a/metrics":
            return httpx.Response(422, json={"detail": "invalid chip id"})
        return httpx.Response(500, json={"detail": "unexpected"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        with pytest.raises(QDashValidationError):
            client.get_chip_metrics("chip-a")
    finally:
        client.close()


def test_get_task_results_timeseries_returns_object() -> None:
    payload = {
        "data": {
            "Q00": [
                {
                    "parameter_name": "t1",
                    "value": 12.5,
                    "value_type": "float",
                    "calibrated_at": "2026-01-01T00:00:00Z",
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/task-results/timeseries":
            assert request.url.params.get("chip_id") == "chip-a"
            assert request.url.params.get("parameter") == "t1"
            assert request.url.params.get("tag") == "calibration"
            assert request.url.params.get("qid") == "Q00"
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        series = client.get_task_results_timeseries(
            chip_id="chip-a",
            parameter="t1",
            tag="calibration",
            qid="Q00",
            start_at="2026-01-01T00:00:00Z",
            end_at="2026-01-02T00:00:00Z",
        )
        assert isinstance(series, TimeSeriesData)
        assert "Q00" in series.data
        assert series.data["Q00"][0].parameter_name == "t1"
    finally:
        client.close()


def test_get_task_results_timeseries_404_maps_to_not_found_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/task-results/timeseries":
            return httpx.Response(404, json={"detail": "missing"})
        return httpx.Response(500, json={"detail": "unexpected"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        with pytest.raises(QDashNotFoundError):
            client.get_task_results_timeseries(
                chip_id="chip-a",
                parameter="t1",
                start_at="2026-01-01T00:00:00Z",
                end_at="2026-01-02T00:00:00Z",
            )
    finally:
        client.close()


def test_get_task_results_timeseries_422_maps_to_validation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/task-results/timeseries":
            return httpx.Response(422, json={"detail": "invalid query"})
        return httpx.Response(500, json={"detail": "unexpected"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        with pytest.raises(QDashValidationError):
            client.get_task_results_timeseries(
                chip_id="chip-a",
                parameter="t1",
                start_at="2026-01-01T00:00:00Z",
                end_at="2026-01-02T00:00:00Z",
            )
    finally:
        client.close()


def test_header_population_with_api_token() -> None:
    client = _build_client(
        httpx.MockTransport(lambda _request: httpx.Response(200, json=[])),
        api_token="api-token",
    )
    client.config.project_id = "proj"
    client.config.cf_access_client_id = "cf-id"
    client.config.cf_access_client_secret = "cf-secret"  # noqa: S105

    try:
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer api-token"
        assert headers["X-Project-Id"] == "proj"
        assert headers["CF-Access-Client-Id"] == "cf-id"
        assert headers["CF-Access-Client-Secret"] == "cf-secret"
    finally:
        client.close()


def test_retry_classifier_and_exception_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_PASSWORD", "secret")

    client = _build_client(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"access_token": "ok"}))
    )
    try:
        assert not client._is_retryable_status(429)
        assert not client._is_retryable_status(503)
        assert not client._is_retryable_status(404)

        request = httpx.Request("GET", "http://qdash.local/x")
        assert isinstance(
            client._raise_for_response(httpx.Response(401, request=request)), QDashTransportError
        )
        assert isinstance(
            client._raise_for_response(httpx.Response(422, request=request)), QDashValidationError
        )
        assert isinstance(
            client._raise_for_response(httpx.Response(404, request=request)), QDashNotFoundError
        )
        assert isinstance(
            client._raise_for_response(httpx.Response(503, request=request)), QDashTransportError
        )
    finally:
        client.close()


def test_backoff_obeys_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_PASSWORD", "secret")

    client = _build_client(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"access_token": "ok"}))
    )
    try:
        request = httpx.Request("GET", "http://qdash.local/metrics")
        response = httpx.Response(429, request=request, headers={"Retry-After": "3"})
        delay = client._retry_delay_for_attempt(1, response)
        assert delay == 3.0
    finally:
        client.close()


def test_backoff_without_retry_after_uses_exponential_with_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QDASH_PASSWORD", "secret")
    monkeypatch.setattr("qdash.client.services.client.random.uniform", lambda _a, _b: 0.0)

    client = _build_client(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"access_token": "ok"}))
    )
    try:
        assert client._retry_delay_for_attempt(1) == 0.01
        assert client._retry_delay_for_attempt(2) == 0.02
        assert client._retry_delay_for_attempt(10) == 0.05
    finally:
        client.close()


def test_normalize_supports_qubit_and_coupling_and_filters_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QDASH_PASSWORD", "secret")

    client = _build_client(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"access_token": "ok"}))
    )
    try:
        payload = {
            "qubit_metrics": [
                {
                    "qubit_id": "Q00",
                    "metrics": {
                        "t1": {"value": 12.5, "unit": "us", "observed_at": "2026-01-01T00:00:00Z"},
                        "bad_text": {"value": "x"},
                        "bad_null": {"value": None},
                    },
                }
            ],
            "coupling_metrics": [
                {
                    "entity_type": "coupling",
                    "entity_id": "Q00-Q01",
                    "metric_name": "cz_fidelity",
                    "value": 0.991,
                    "unit": None,
                }
            ],
        }

        records = client.normalize_chip_metrics("chip-a", payload)
        assert len(records) == 2

        qubit_record = next(record for record in records if record.entity_type == "qubit")
        assert qubit_record.metric_name == "t1"
        assert qubit_record.entity_id == "Q00"
        assert qubit_record.value == 12.5

        coupling_record = next(record for record in records if record.entity_type == "coupling")
        assert coupling_record.metric_name == "cz_fidelity"
        assert coupling_record.entity_id == "Q00-Q01"
        assert coupling_record.unit == ""
    finally:
        client.close()


@pytest.mark.asyncio
async def test_async_methods_with_monkeypatched_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyResponse:
        def __init__(self, status_code: int, payload: object) -> None:
            self.status_code = status_code
            self._payload = payload
            self.headers: dict[str, str] = {}
            self.request = httpx.Request("GET", "http://qdash.local/async")

        def json(self) -> object:
            return self._payload

    class DummyAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self) -> DummyAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(
            self,
            path: str,
            *,
            headers: dict[str, str] | None = None,
            params: dict[str, object] | None = None,
        ) -> DummyResponse:
            if path == "/chips":
                return DummyResponse(200, {"chips": [{"chip_id": "chip-a"}], "total": 1})
            if path == "/task-results/timeseries":
                assert params is not None
                assert params.get("chip_id") == "chip-a"
                return DummyResponse(
                    200,
                    {
                        "data": {
                            "Q00": [
                                {
                                    "parameter_name": "t1",
                                    "value": 12.5,
                                    "value_type": "float",
                                    "calibrated_at": "2026-01-01T00:00:00Z",
                                }
                            ]
                        }
                    },
                )
            if path == "/metrics/config":
                return DummyResponse(
                    200,
                    {
                        "qubit_metrics": {"t1": {"title": "T1"}},
                        "coupling_metrics": {"cz_fidelity": {"title": "CZ"}},
                        "color_scale": {"colors": ["#000", "#fff"]},
                    },
                )
            return DummyResponse(404, {"detail": "missing"})

    monkeypatch.setattr("qdash.client.services.client.httpx.AsyncClient", DummyAsyncClient)

    client = _build_client(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"access_token": "ok"})),
        api_token="api-token",
    )
    try:
        chips = await client.list_chips_async()
        assert isinstance(chips, ListChipsResponse)
        assert [chip.chip_id for chip in chips.chips] == ["chip-a"]

        series = await client.get_task_results_timeseries_async(
            chip_id="chip-a",
            parameter="t1",
            start_at="2026-01-01T00:00:00Z",
            end_at="2026-01-02T00:00:00Z",
        )
        assert isinstance(series, TimeSeriesData)
        assert "Q00" in series.data
        assert series.data["Q00"][0].parameter_name == "t1"

        metrics_config = await client.get_metrics_config_async()
        assert "qubit_metrics" in metrics_config
        assert "coupling_metrics" in metrics_config
        assert "color_scale" in metrics_config
    finally:
        client.close()
