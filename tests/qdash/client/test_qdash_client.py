from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import httpx

if TYPE_CHECKING:
    from pathlib import Path
import pytest

from qdash.client import (
    AiReviewListResponse,
    AiReviewRunDetailResponse,
    AiReviewRunListResponse,
    CancelExecutionResponse,
    ChipResponse,
    CouplingResponse,
    ExecuteFlowResponse,
    FileTreeNode,
    FlowTemplate,
    FlowTemplateWithCode,
    LatestTaskResultResponse,
    ListChipsResponse,
    ListCouplingsResponse,
    ListExecutionsResponse,
    ListFlowsResponse,
    ListIssuesResponse,
    ListQubitsResponse,
    ListTaskKnowledgeResponse,
    ListTaskResponse,
    NoteModel,
    QDashClient,
    QDashConfig,
    QDashConfigError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
    QubitResponse,
    SaveFlowResponse,
    ScheduleFlowResponse,
    TaskKnowledgeResponse,
    TaskResultExcludeResponse,
    TaskResultListResponse,
    TaskResultResponse,
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


def test_client_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_BASE_URL", "http://env.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "env-token")

    client = QDashClient.from_env()
    try:
        assert client.config.base_url == "http://env.local"
        assert client.config.api_token == "env-token"  # noqa: S105
    finally:
        client.close()


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


def test_client_from_profile(tmp_path: Path) -> None:
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[local]
base_url = http://local.example/
api_token = local-token
""".strip()
    )

    client = QDashClient.from_profile("local", path=config_file)
    try:
        assert client.config.base_url == "http://local.example"
        assert client.config.api_token == "local-token"  # noqa: S105
    finally:
        client.close()


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
            assert request.headers["Content-Type"].startswith("application/x-www-form-urlencoded")
            assert request.content == b"username=tester&password=secret"
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


def test_get_default_chip_prefers_latest_active_chip() -> None:
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
        assert chip.chip_id == "chip-active-latest"
        assert client.get_default_chip_id() == "chip-active-latest"
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


def test_get_default_chip_uses_undated_chip_only_when_needed() -> None:
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
        assert client.get_default_chip().chip_id == "chip-dated"
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


def test_list_task_results_sends_common_filters() -> None:
    payload = {
        "items": [
            {
                "task_id": "task-1",
                "task_name": "t1",
                "qid": "Q00",
                "chip_id": "chip-a",
                "status": "success",
                "execution_id": "exec-1",
            }
        ],
        "total": 1,
        "skip": 5,
        "limit": 10,
        "status_counts": {"success": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/task-results":
            assert request.url.params.get("status") == "success"
            assert request.url.params.get("chip_id") == "chip-a"
            assert request.url.params.get("task_name") == "t1"
            assert request.url.params.get("qid") == "Q00"
            assert request.url.params.get("execution_id") == "exec-1"
            assert request.url.params.get("username") == "operator"
            assert request.url.params.get("start_from") == "2026-01-01T00:00:00Z"
            assert request.url.params.get("start_to") == "2026-01-02T00:00:00Z"
            assert request.url.params.get("message_contains") == "done"
            assert request.url.params.get("skip") == "5"
            assert request.url.params.get("limit") == "10"
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        results = client.list_task_results(
            status="success",
            chip_id="chip-a",
            task_name="t1",
            qid="Q00",
            execution_id="exec-1",
            username="operator",
            start_from="2026-01-01T00:00:00Z",
            start_to="2026-01-02T00:00:00Z",
            message_contains="done",
            skip=5,
            limit=10,
        )
        assert isinstance(results, TaskResultListResponse)
        assert results.items[0].task_id == "task-1"
    finally:
        client.close()


def test_task_result_latest_and_history_methods_use_expected_paths() -> None:
    latest_payload = {"task_name": "t1", "result": {}}
    history_payload = {"name": "t1", "data": {}}
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.url.params.get("chip_id") == "chip-a"
        assert request.url.params.get("task") == "t1"
        if request.url.path.endswith("/history"):
            assert request.url.params.get("date") == "20260101"
            return httpx.Response(200, json=history_payload)
        return httpx.Response(200, json=latest_payload)

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        latest = client.get_qubit_latest_task_results(chip_id="chip-a", task="t1")
        qubit_history = client.get_qubit_task_history(
            chip_id="chip-a",
            qid="Q00",
            task="t1",
            date="20260101",
        )
        coupling_latest = client.get_coupling_latest_task_results(
            chip_id="chip-a",
            task="t1",
        )
        coupling_history = client.get_coupling_task_history(
            chip_id="chip-a",
            coupling_id="Q00-Q01",
            task="t1",
            date="20260101",
        )

        assert isinstance(latest, LatestTaskResultResponse)
        assert qubit_history.name == "t1"
        assert coupling_latest.task_name == "t1"
        assert coupling_history.name == "t1"
        assert seen_paths == [
            "/task-results/qubits/latest",
            "/task-results/qubits/Q00/history",
            "/task-results/couplings/latest",
            "/task-results/couplings/Q00-Q01/history",
        ]
    finally:
        client.close()


def test_agent_read_only_resource_methods_return_models_and_objects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        match request.url.path:
            case "/projects":
                return httpx.Response(200, json={"projects": [], "total": 0})
            case "/files/tree":
                return httpx.Response(
                    200,
                    json=[{"name": "flows", "path": "flows", "type": "directory"}],
                )
            case "/files/git/status":
                return httpx.Response(200, json={"branch": "main", "dirty": False})
            case "/issues":
                assert request.url.params.get("task_id") == "task-1"
                assert request.url.params.get("is_closed") == "false"
                return httpx.Response(200, json={"issues": [], "total": 0, "skip": 0, "limit": 20})
            case "/issue-knowledge":
                assert request.url.params.get("status") == "approved"
                return httpx.Response(200, json={"items": [], "total": 0, "skip": 0, "limit": 20})
            case "/flows":
                return httpx.Response(200, json={"flows": []})
            case "/executions":
                assert request.url.params.get("chip_id") == "chip-a"
                return httpx.Response(
                    200,
                    json={"executions": [], "total": 0, "skip": 0, "limit": 20},
                )
            case "/provenance/stats":
                return httpx.Response(
                    200,
                    json={
                        "total_entities": 0,
                        "total_activities": 0,
                        "total_relations": 0,
                        "relation_counts": {},
                        "recent_entities": [],
                    },
                )
            case "/provenance/changes":
                assert request.url.params.get("parameter_names") == "t1"
                return httpx.Response(200, json={"changes": [], "total_count": 0})
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        assert client.list_projects().total == 0
        tree = client.get_files_tree()
        assert isinstance(tree[0], FileTreeNode)
        assert client.get_git_status()["branch"] == "main"
        assert isinstance(
            client.list_issues(task_id="task-1", is_closed=False, limit=20),
            ListIssuesResponse,
        )
        assert client.list_issue_knowledge(status="approved", limit=20).items == []
        assert isinstance(client.list_flows(), ListFlowsResponse)
        assert isinstance(
            client.list_executions(chip_id="chip-a"),
            ListExecutionsResponse,
        )
        assert client.get_provenance_stats().total_entities == 0
        assert client.get_provenance_changes(parameter_names=["t1"]).total_count == 0
    finally:
        client.close()


def test_chip_topology_read_helpers_return_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        match request.url.path:
            case "/chips/chip-a/qubits":
                assert request.url.params.get("qids") == "Q00"
                assert request.url.params.get("offset") == "5"
                assert request.url.params.get("limit") == "10"
                return httpx.Response(
                    200,
                    json={
                        "qubits": [{"qid": "Q00", "chip_id": "chip-a", "status": "ready"}],
                        "total": 1,
                        "offset": 5,
                        "limit": 10,
                    },
                )
            case "/chips/chip-a/qubits/Q00":
                return httpx.Response(
                    200,
                    json={"qid": "Q00", "chip_id": "chip-a", "data": {"t1": 12.5}},
                )
            case "/chips/chip-a/couplings":
                assert request.url.params.get("offset") == "0"
                assert request.url.params.get("limit") == "25"
                return httpx.Response(
                    200,
                    json={
                        "couplings": [{"qid": "Q00-Q01", "chip_id": "chip-a"}],
                        "total": 1,
                        "offset": 0,
                        "limit": 25,
                    },
                )
            case "/chips/chip-a/couplings/Q00-Q01":
                return httpx.Response(
                    200,
                    json={"qid": "Q00-Q01", "chip_id": "chip-a", "status": "ready"},
                )
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        qubits = client.list_chip_qubits("chip-a", qids=["Q00"], offset=5, limit=10)
        qubit = client.get_chip_qubit(chip_id="chip-a", qid="Q00")
        couplings = client.list_chip_couplings("chip-a", limit=25)
        coupling = client.get_chip_coupling(chip_id="chip-a", coupling_id="Q00-Q01")

        assert isinstance(qubits, ListQubitsResponse)
        assert isinstance(qubit, QubitResponse)
        assert qubit.data["t1"] == 12.5
        assert isinstance(couplings, ListCouplingsResponse)
        assert isinstance(coupling, CouplingResponse)
    finally:
        client.close()


def test_task_file_flow_and_ai_review_read_helpers_return_models() -> None:
    issue_payload = {
        "id": "issue-1",
        "task_id": "task-1",
        "username": "operator",
        "title": "Bad fit",
        "content": "Needs review",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    task_result_payload = {
        "task_id": "task-1",
        "task_name": "t1",
        "qid": "Q00",
        "chip_id": "chip-a",
        "status": "success",
        "execution_id": "exec-1",
        "figure_path": [],
        "json_figure_path": [],
        "input_parameters": {},
        "output_parameters": {"t1": 12.5},
    }
    flow_template_payload = {
        "id": "rabi",
        "name": "Rabi",
        "description": "Run Rabi calibration",
        "category": "calibration",
        "filename": "rabi.py",
        "function_name": "rabi",
    }
    knowledge_payload = {
        "name": "t1",
        "category": "qubit",
        "summary": "T1 summary",
        "what_it_measures": "Energy relaxation",
        "physical_principle": "Relaxation decay",
        "expected_result": {"description": "Exponential decay"},
        "evaluation_criteria": "Check fit quality",
        "failure_modes": [{"severity": "warning", "description": "Noisy curve"}],
        "tips": ["Inspect the fitted decay"],
        "prompt_text": "Review t1",
    }
    review_run_payload: dict[str, object] = {
        "review_run_id": "run-1",
        "trigger_type": "manual_chip_bulk",
        "chip_id": "chip-a",
        "task_name": "t1",
        "entity_type": "qubit",
        "execution_ids": ["exec-1"],
        "requested_by": "operator",
        "requested_at": "2026-01-01T00:00:00Z",
        "completed_at": None,
        "model": "gpt-test",
        "total": 0,
        "completed_count": 0,
        "failed_count": 0,
        "running_count": 0,
        "requested_count": 0,
        "decision_counts": {},
        "status_counts": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        match request.url.path:
            case "/files/content":
                assert request.url.params.get("path") == "flows/demo.py"
                return httpx.Response(200, json={"path": "flows/demo.py", "content": "pass"})
            case "/task-results/task-1/issues":
                return httpx.Response(200, json=[issue_payload])
            case "/flows/templates":
                return httpx.Response(200, json=[flow_template_payload])
            case "/flows/templates/rabi":
                return httpx.Response(
                    200, json={**flow_template_payload, "code": "def rabi(): pass"}
                )
            case "/flows/helpers":
                return httpx.Response(200, json=["common.py"])
            case "/flows/helpers/common.py":
                return httpx.Response(200, text="def helper(): pass")
            case "/tasks":
                assert request.url.params.get("backend") == "qubex"
                return httpx.Response(
                    200,
                    json={
                        "tasks": [
                            {
                                "name": "t1",
                                "description": "Measure T1",
                                "task_type": "qubit",
                                "input_parameters": {},
                                "output_parameters": {},
                            }
                        ]
                    },
                )
            case "/tasks/task-1/result":
                return httpx.Response(200, json=task_result_payload)
            case "/task-knowledge":
                return httpx.Response(
                    200,
                    json={
                        "items": [{"name": "t1", "category": "qubit", "summary": "T1 summary"}],
                        "categories": {"qubit": "Qubit"},
                    },
                )
            case "/tasks/t1/knowledge":
                return httpx.Response(200, json=knowledge_payload)
            case "/tasks/t1/knowledge/markdown":
                return httpx.Response(200, text="# T1")
            case "/task-results/task-1/note":
                return httpx.Response(
                    200,
                    json={
                        "content": "reviewed",
                        "updated_by": "operator",
                        "updated_at": "2026-01-01T00:00:00Z",
                    },
                )
            case "/task-results/ai-review":
                assert request.url.params.get("chip_id") == "chip-a"
                assert request.url.params.get("task_name") == "t1"
                assert request.url.params.get("status") == "completed"
                assert request.url.params.get("decision") == "accept"
                assert request.url.params.get("latest_only") == "true"
                return httpx.Response(
                    200,
                    json={
                        "items": [],
                        "total": 0,
                        "skip": 2,
                        "limit": 5,
                        "decision_counts": {},
                        "status_counts": {},
                    },
                )
            case "/task-results/ai-review/runs":
                assert request.url.params.get("chip_id") == "chip-a"
                assert request.url.params.get("task_name") == "t1"
                return httpx.Response(
                    200,
                    json={"items": [review_run_payload], "total": 1, "skip": 0, "limit": 10},
                )
            case "/task-results/ai-review/runs/run-1":
                return httpx.Response(200, json={"run": review_run_payload, "items": []})
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        assert client.get_file_content("flows/demo.py")["content"] == "pass"
        assert client.list_task_result_issues("task-1")[0].id == "issue-1"
        assert isinstance(client.list_flow_templates()[0], FlowTemplate)
        assert isinstance(client.get_flow_template("rabi"), FlowTemplateWithCode)
        assert client.list_flow_helper_files() == ["common.py"]
        assert client.get_flow_helper_file("common.py") == "def helper(): pass"
        assert isinstance(client.list_tasks(backend="qubex"), ListTaskResponse)
        assert isinstance(client.get_task_result("task-1"), TaskResultResponse)
        assert isinstance(client.list_task_knowledge(), ListTaskKnowledgeResponse)
        assert isinstance(client.get_task_knowledge("t1"), TaskKnowledgeResponse)
        assert client.get_task_knowledge_markdown("t1") == "# T1"
        assert isinstance(client.get_task_note("task-1"), NoteModel)
        assert isinstance(
            client.list_task_result_ai_reviews(
                chip_id="chip-a",
                task_name="t1",
                status="completed",
                decision="accept",
                latest_only=True,
                skip=2,
                limit=5,
            ),
            AiReviewListResponse,
        )
        assert isinstance(
            client.list_task_result_ai_review_runs(chip_id="chip-a", task_name="t1", limit=10),
            AiReviewRunListResponse,
        )
        assert isinstance(client.get_task_result_ai_review_run("run-1"), AiReviewRunDetailResponse)
    finally:
        client.close()


def test_file_and_git_write_helpers_send_json_bodies() -> None:
    def request_json(request: httpx.Request) -> dict[str, object]:
        return cast("dict[str, object]", json.loads(request.content.decode() or "{}"))

    def handler(request: httpx.Request) -> httpx.Response:
        match (request.method, request.url.path):
            case ("PUT", "/files/content"):
                assert request_json(request) == {"path": "flows/demo.py", "content": "print('ok')"}
                return httpx.Response(200, json={"message": "saved", "path": "flows/demo.py"})
            case ("POST", "/files/validate"):
                assert request_json(request) == {"content": "print('ok')", "file_type": "flow"}
                return httpx.Response(200, json={"valid": True})
            case ("POST", "/files/git/pull"):
                assert request_json(request) == {}
                return httpx.Response(200, json={"status": "pulled"})
            case ("POST", "/files/git/push"):
                assert request_json(request) == {"commit_message": "Update flow"}
                return httpx.Response(200, json={"status": "pushed"})
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        assert client.save_file_content(path="flows/demo.py", content="print('ok')")["message"] == (
            "saved"
        )
        assert (
            client.validate_file_content(content="print('ok')", file_type="flow")["valid"] is True
        )
        assert client.git_pull_config()["status"] == "pulled"
        assert client.git_push_config(commit_message="Update flow")["status"] == "pushed"
    finally:
        client.close()


def test_flow_and_execution_write_helpers_return_models() -> None:
    execute_payload = {
        "execution_id": "exec-1",
        "flow_run_url": "https://prefect.local/runs/exec-1",
        "qdash_ui_url": "https://qdash.local/executions/exec-1",
        "message": "started",
    }

    def request_json(request: httpx.Request) -> dict[str, object]:
        return cast("dict[str, object]", json.loads(request.content.decode() or "{}"))

    def handler(request: httpx.Request) -> httpx.Response:
        match (request.method, request.url.path):
            case ("POST", "/flows"):
                body = request_json(request)
                assert body["name"] == "demo"
                assert body["code"] == "def demo(): pass"
                assert body["chip_id"] == "chip-a"
                return httpx.Response(
                    200,
                    json={
                        "name": "demo",
                        "file_path": "flows/demo.py",
                        "message": "saved",
                    },
                )
            case ("POST", "/flows/demo/execute"):
                assert request_json(request) == {"parameters": {"shots": 10}}
                return httpx.Response(200, json=execute_payload)
            case ("POST", "/flows/demo/schedule"):
                assert request_json(request) == {
                    "cron": "0 2 * * *",
                    "parameters": {"shots": 10},
                    "active": True,
                    "timezone": "Asia/Tokyo",
                }
                return httpx.Response(
                    200,
                    json={
                        "schedule_id": "schedule-1",
                        "flow_name": "demo",
                        "schedule_type": "cron",
                        "cron": "0 2 * * *",
                        "active": True,
                        "message": "scheduled",
                    },
                )
            case ("POST", "/executions/run-1/cancel"):
                return httpx.Response(
                    200,
                    json={
                        "execution_id": "run-1",
                        "status": "cancelled",
                        "message": "cancelled",
                    },
                )
            case ("POST", "/executions/exec-1/re-execute"):
                return httpx.Response(200, json=execute_payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        assert isinstance(
            client.save_flow(name="demo", code="def demo(): pass", chip_id="chip-a"),
            SaveFlowResponse,
        )
        assert isinstance(
            client.execute_flow("demo", parameters={"shots": 10}),
            ExecuteFlowResponse,
        )
        assert isinstance(
            client.schedule_flow("demo", cron="0 2 * * *", parameters={"shots": 10}),
            ScheduleFlowResponse,
        )
        assert isinstance(client.cancel_execution("run-1"), CancelExecutionResponse)
        assert client.re_execute_execution("exec-1").execution_id == "exec-1"
    finally:
        client.close()


def test_task_result_and_issue_write_helpers_return_models() -> None:
    issue_payload = {
        "id": "issue-1",
        "task_id": "task-1",
        "username": "operator",
        "title": "Bad fit",
        "content": "Needs review",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    knowledge_payload = {
        "id": "knowledge-1",
        "issue_id": "issue-1",
        "task_id": "task-1",
        "task_name": "t1",
        "title": "Bad fit",
        "status": "draft",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    execute_payload = {
        "execution_id": "exec-1",
        "flow_run_url": "https://prefect.local/runs/exec-1",
        "qdash_ui_url": "https://qdash.local/executions/exec-1",
        "message": "started",
    }

    def request_json(request: httpx.Request) -> dict[str, object]:
        return cast("dict[str, object]", json.loads(request.content.decode() or "{}"))

    def handler(request: httpx.Request) -> httpx.Response:
        match (request.method, request.url.path):
            case ("PUT", "/task-results/task-1/note"):
                assert request_json(request) == {"content": "reviewed"}
                return httpx.Response(
                    200,
                    json={
                        "content": "reviewed",
                        "updated_by": "operator",
                        "updated_at": "2026-01-01T00:00:00Z",
                    },
                )
            case ("POST", "/task-results/task-1/exclude"):
                assert request_json(request) == {"excluded": True, "reason": "bad fit"}
                return httpx.Response(
                    200,
                    json={
                        "task_id": "task-1",
                        "excluded": True,
                        "excluded_reason": "bad fit",
                        "excluded_by_user_id": "user-1",
                        "excluded_by": "operator",
                        "excluded_at": "2026-01-01T00:00:00Z",
                    },
                )
            case ("POST", "/task-results/task-1/re-execute"):
                assert request_json(request) == {
                    "parameter_overrides": {"run": {"shots": 10}},
                    "update_params": False,
                    "reconfigure": True,
                }
                return httpx.Response(200, json=execute_payload)
            case ("POST", "/task-results/task-1/issues"):
                assert request_json(request) == {"title": "Bad fit", "content": "Needs review"}
                return httpx.Response(201, json=issue_payload)
            case ("PATCH", "/issues/issue-1"):
                assert request_json(request) == {"content": "Updated"}
                return httpx.Response(200, json={**issue_payload, "content": "Updated"})
            case ("PATCH", "/issues/issue-1/close"):
                return httpx.Response(200, json={"message": "closed"})
            case ("PATCH", "/issues/issue-1/reopen"):
                return httpx.Response(200, json={"message": "reopened"})
            case ("PATCH", "/issue-knowledge/knowledge-1"):
                assert request_json(request) == {"title": "Updated case"}
                return httpx.Response(200, json={**knowledge_payload, "title": "Updated case"})
            case ("PATCH", "/issue-knowledge/knowledge-1/approve"):
                return httpx.Response(200, json={**knowledge_payload, "status": "approved"})
            case ("PATCH", "/issue-knowledge/knowledge-1/reject"):
                return httpx.Response(200, json={**knowledge_payload, "status": "rejected"})
            case ("POST", "/issues/issue-1/extract-knowledge"):
                return httpx.Response(201, json=knowledge_payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        assert client.upsert_task_note("task-1", content="reviewed").content == "reviewed"
        assert isinstance(
            client.set_task_result_excluded("task-1", excluded=True, reason="bad fit"),
            TaskResultExcludeResponse,
        )
        assert (
            client.re_execute_task_result(
                "task-1",
                parameter_overrides={"run": {"shots": 10}},
                update_params=False,
                reconfigure=True,
            ).execution_id
            == "exec-1"
        )
        assert (
            client.create_task_result_issue(
                task_id="task-1",
                title="Bad fit",
                content="Needs review",
            ).id
            == "issue-1"
        )
        assert client.update_issue("issue-1", content="Updated").content == "Updated"
        assert client.close_issue("issue-1").message == "closed"
        assert client.reopen_issue("issue-1").message == "reopened"
        assert (
            client.update_issue_knowledge(
                "knowledge-1",
                fields={"title": "Updated case"},
            ).title
            == "Updated case"
        )
        assert client.approve_issue_knowledge("knowledge-1").status == "approved"
        assert client.reject_issue_knowledge("knowledge-1").status == "rejected"
        assert client.extract_issue_knowledge("issue-1").id == "knowledge-1"
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


def test_agent_session_client_methods() -> None:
    session_payload = {
        "session_id": "session-1",
        "project_id": "project-1",
        "chip_id": "chip-a",
        "created_by": "tester",
        "policy": {
            "qids": ["Q00"],
            "allowed_tasks": ["CheckT1"],
            "allowed_actions": ["run_task"],
            "allowed_overrides": {"shots": {"minimum": 1000, "maximum": 5000}},
            "max_actions": 10,
        },
        "skill_name": "bringup",
        "skill_version": "1",
        "skill_hash": "sha256:test",
        "model_name": "local",
        "status": "active",
        "state_version": 0,
        "action_count": 0,
        "created_at": "2026-07-13T00:00:00Z",
        "updated_at": "2026-07-13T00:00:00Z",
        "expires_at": "2026-07-13T01:00:00Z",
    }
    action_payload = {
        "action_id": "action-1",
        "session_id": "session-1",
        "idempotency_key": "key-1",
        "action_type": "run_task",
        "task_name": "CheckT1",
        "qids": ["Q00"],
        "parameter_overrides": {"shots": 2000},
        "diagnosis": "retry",
        "decision": "authorized",
        "reason": "allowed",
        "execution_status": "not_started",
        "state_version_before": 0,
        "state_version_after": 1,
        "created_at": "2026-07-13T00:00:01Z",
    }
    gate_payload = {
        "session_id": "session-1",
        "parameter_name": "shots",
        "value": 2000,
        "accepted": True,
        "reason": "candidate passed deterministic bounds gate",
        "minimum": 1000,
        "maximum": 5000,
    }
    candidate_payload = {
        "session_id": "session-1",
        "action_id": "action-1",
        "execution_id": "operation-1",
        "task_id": "task-1",
        "task_name": "CheckT1",
        "qid": "Q00",
        "source_parameter_name": "shots",
        "parameter_name": "shots",
        "value": 2000,
        "error": 0,
        "unit": "",
        "value_type": "int",
        "accepted": True,
        "reason": "candidate passed deterministic bounds gate",
        "minimum": 1000,
        "maximum": 5000,
    }
    commit_payload = {
        "commit_id": "commit-1",
        "session_id": "session-1",
        "action_id": "action-1",
        "idempotency_key": "commit-key-1",
        "execution_id": "operation-1",
        "task_id": "task-1",
        "task_name": "CheckT1",
        "qid": "Q00",
        "parameter_name": "shots",
        "value": 2000,
        "status": "committed",
        "reason": "committed",
        "before_snapshot": None,
        "after_snapshot": {"value": 2000},
        "committed_by": "tester",
        "state_version_before": 1,
        "state_version_after": 2,
        "created_at": "2026-07-13T00:00:02Z",
        "committed_at": "2026-07-13T00:00:02Z",
    }

    applied_commit_payload = {
        **commit_payload,
        "backend_status": "applied",
        "backend_operation_id": "backend-operation-1",
        "backend_name": "fake",
        "backend_target_files": ["shots.yaml"],
        "backend_changed_files": ["shots.yaml"],
        "backend_verified": True,
        "backend_git_commit": "abc12345",
        "backend_error": "",
        "backend_requested_at": "2026-07-13T00:00:03Z",
        "backend_applied_at": "2026-07-13T00:00:04Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/agent-sessions":
            assert request.read()
            return httpx.Response(201, json=session_payload)
        if request.method == "GET" and request.url.path == "/agent-sessions/session-1":
            return httpx.Response(200, json=session_payload)
        if (
            request.method == "POST"
            and request.url.path == "/agent-sessions/session-1/candidate-gate"
        ):
            assert json.loads(request.read()) == {"parameter_name": "shots", "value": 2000}
            return httpx.Response(200, json=gate_payload)
        if request.method == "POST" and request.url.path == "/agent-sessions/session-1/actions":
            assert request.read()
            return httpx.Response(201, json=action_payload)
        if (
            request.method == "POST"
            and request.url.path
            == "/agent-sessions/session-1/actions/action-1/candidates/shots/commit"
        ):
            assert json.loads(request.read()) == {
                "idempotency_key": "commit-key-1",
                "expected_state_version": 1,
                "task_id": "task-1",
            }
            return httpx.Response(201, json=commit_payload)
        if (
            request.method == "POST"
            and request.url.path == "/agent-sessions/session-1/commits/commit-1/apply"
        ):
            assert json.loads(request.read()) == {
                "idempotency_key": "apply-key-1",
                "expected_state_version": 2,
                "push_to_github": True,
            }
            return httpx.Response(200, json=applied_commit_payload)
        if (
            request.method == "GET"
            and request.url.path == "/agent-sessions/session-1/commits/commit-1"
        ):
            return httpx.Response(200, json=applied_commit_payload)
        if (
            request.method == "GET"
            and request.url.path == "/agent-sessions/session-1/actions/action-1/candidates"
        ):
            return httpx.Response(
                200,
                json={"items": [candidate_payload], "total": 1},
            )
        if (
            request.method == "GET"
            and request.url.path == "/agent-sessions/session-1/actions/action-1"
        ):
            return httpx.Response(200, json=action_payload)
        if request.method == "GET" and request.url.path == "/agent-sessions/session-1/actions":
            return httpx.Response(200, json={"items": [action_payload], "total": 1})
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        session = client.create_agent_session(
            chip_id="chip-a",
            policy=cast("dict[str, Any]", session_payload["policy"]),
        )
        assert session.session_id == "session-1"
        assert client.get_agent_session("session-1").state_version == 0
        gate = client.evaluate_agent_candidate_gate(
            "session-1",
            parameter_name="shots",
            value=2000,
        )
        assert gate.accepted
        assert gate.minimum == 1000
        action = client.submit_agent_action(
            "session-1",
            idempotency_key="key-1",
            expected_state_version=0,
            action_type="run_task",
            task_name="CheckT1",
            qids=["Q00"],
            parameter_overrides={"shots": 2000},
        )
        assert action.action_id == "action-1"
        assert client.get_agent_action("session-1", "action-1").action_id == "action-1"
        candidates = client.list_agent_action_candidates("session-1", "action-1")
        assert candidates[0].execution_id == "operation-1"
        assert candidates[0].parameter_name == "shots"
        commit = client.commit_agent_action_candidate(
            "session-1",
            "action-1",
            "shots",
            idempotency_key="commit-key-1",
            expected_state_version=1,
            task_id="task-1",
        )
        assert commit.status == "committed"
        assert commit.state_version_after == 2
        applied = client.apply_agent_candidate_commit(
            "session-1",
            "commit-1",
            idempotency_key="apply-key-1",
            expected_state_version=2,
        )
        assert applied.backend_verified is True
        assert (
            client.get_agent_candidate_commit("session-1", "commit-1").backend_git_commit
            == "abc12345"
        )
        assert [item.action_id for item in client.list_agent_actions("session-1")] == ["action-1"]
    finally:
        client.close()


def test_agent_polling_helpers_handle_eventual_consistency() -> None:
    action_calls = 0
    execution_calls = 0
    action_payload: dict[str, Any] = {
        "action_id": "action-1",
        "session_id": "session-1",
        "idempotency_key": "key-1",
        "action_type": "run_task",
        "task_name": "CheckT1",
        "qids": ["Q00"],
        "parameter_overrides": {},
        "diagnosis": "",
        "decision": "authorized",
        "reason": "allowed",
        "execution_status": "dispatching",
        "operation_id": None,
        "state_version_before": 0,
        "state_version_after": 1,
        "created_at": "2026-07-13T00:00:01Z",
    }
    execution_payload = {
        "name": "agent-execution",
        "status": "completed",
        "flow_name": "re-execute:CheckT1",
        "username": "tester",
        "task": [],
        "note": {},
        "tags": ["agent-session:session-1"],
        "chip_id": "chip-a",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal action_calls, execution_calls
        if request.url.path == "/agent-sessions/session-1/actions/action-1":
            action_calls += 1
            payload = dict(action_payload)
            if action_calls >= 2:
                payload["execution_status"] = "queued"
                payload["operation_id"] = "operation-1"
            if action_calls >= 3:
                payload["execution_status"] = "completed"
                payload["execution_id"] = "execution-1"
            return httpx.Response(200, json=payload)
        if request.url.path == "/executions/execution-1":
            execution_calls += 1
            if execution_calls == 1:
                return httpx.Response(404, json={"detail": "not indexed yet"})
            if execution_calls == 2:
                return httpx.Response(200, json={**execution_payload, "status": "running"})
            return httpx.Response(200, json=execution_payload)
        return httpx.Response(404, json={"detail": "missing"})

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        action = client.wait_for_agent_action(
            "session-1",
            "action-1",
            timeout_seconds=1,
            poll_interval_seconds=0,
        )
        linked = client.wait_for_agent_action_execution(
            "session-1",
            "action-1",
            timeout_seconds=1,
            poll_interval_seconds=0,
        )
        execution = client.wait_for_execution(
            "execution-1",
            timeout_seconds=1,
            poll_interval_seconds=0,
        )

        assert action.operation_id == "operation-1"
        assert linked.operation_id == "operation-1"
        assert linked.execution_id == "execution-1"
        assert action_calls == 3
        assert execution.status == "completed"
        assert execution_calls == 3
    finally:
        client.close()


def test_wait_for_agent_candidate_apply_reaches_verified_terminal_state() -> None:
    calls = 0
    base = {
        "commit_id": "commit-1",
        "session_id": "session-1",
        "action_id": "action-1",
        "idempotency_key": "commit-key",
        "execution_id": "operation-1",
        "task_id": "task-1",
        "task_name": "CheckT1",
        "qid": "Q00",
        "parameter_name": "t1",
        "value": 95.0,
        "status": "committed",
        "reason": "committed",
        "committed_by": "tester",
        "state_version_before": 1,
        "state_version_after": 2,
        "created_at": "2026-07-13T00:00:02Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = "queued" if calls == 1 else "applied"
        return httpx.Response(
            200,
            json={**base, "backend_status": status, "backend_verified": status == "applied"},
        )

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        result = client.wait_for_agent_candidate_apply(
            "session-1",
            "commit-1",
            timeout_seconds=1,
            poll_interval_seconds=0,
        )
        assert result.backend_status == "applied"
        assert result.backend_verified is True
        assert calls == 2
    finally:
        client.close()


def test_agent_polling_helpers_timeout() -> None:
    action_payload: dict[str, Any] = {
        "action_id": "action-1",
        "session_id": "session-1",
        "idempotency_key": "key-1",
        "action_type": "run_task",
        "task_name": "CheckT1",
        "qids": ["Q00"],
        "parameter_overrides": {},
        "diagnosis": "",
        "decision": "authorized",
        "reason": "allowed",
        "execution_status": "dispatching",
        "operation_id": None,
        "state_version_before": 0,
        "state_version_after": 1,
        "created_at": "2026-07-13T00:00:01Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=action_payload)

    client = _build_client(httpx.MockTransport(handler), api_token="api-token")
    try:
        with pytest.raises(TimeoutError):
            client.wait_for_agent_action(
                "session-1",
                "action-1",
                timeout_seconds=0,
                poll_interval_seconds=0,
            )
        action_payload["operation_id"] = "operation-1"
        action_payload["execution_status"] = "queued"
        with pytest.raises(TimeoutError):
            client.wait_for_agent_action_execution(
                "session-1",
                "action-1",
                timeout_seconds=0,
                poll_interval_seconds=0,
            )
    finally:
        client.close()
