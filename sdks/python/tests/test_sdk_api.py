"""The generated client under a session: headers, auth, errors, retries and configuration."""

from __future__ import annotations

import json
import ssl
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from test_sdk_session import CHIP, Server, execute_body, pipeline, validate_body

from qdash.sdk import (
    ApiError,
    QDash,
    QDashApiError,
    QDashAuthError,
    QDashConfig,
    QDashConfigError,
    QDashConflictError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
)
from qdash.sdk._generated.errors.unprocessable_entity_error import UnprocessableEntityError
from qdash.sdk.dashboard import Dashboard, Script

if TYPE_CHECKING:
    from pathlib import Path

CHIPS = {"chips": [], "total": 0}


def full_config(**overrides: Any) -> QDashConfig:
    values: dict[str, Any] = {
        "base_url": "http://qdash.local/api/",
        "api_token": "api-token",
        "project_id": "project-a",
        "cf_access_client_id": "cf-id",
        "cf_access_client_secret": "cf-secret",
        "user_agent": "notebook/1.0",
        "timeout_sec": 12.5,
    }
    values.update(overrides)
    return QDashConfig(**values)


def test_generated_resources_carry_the_session_headers() -> None:
    server = Server({("GET", "/api/chips"): [httpx.Response(200, json=CHIPS)]})
    with QDash(full_config(), http_client=server.http_client()) as qdash:
        result = qdash.api.chip.list_chips()

    assert result.total == 0
    request = server.requests[0]
    assert str(request.url) == "http://qdash.local/api/chips"
    assert request.headers["Authorization"] == "Bearer api-token"
    assert request.headers.get_list("X-Project-Id") == ["project-a"]
    assert request.headers["CF-Access-Client-Id"] == "cf-id"
    assert request.headers["CF-Access-Client-Secret"] == "cf-secret"
    assert request.headers["User-Agent"] == "notebook/1.0"
    assert not [name for name in request.headers if name.lower().startswith("x-fern")]
    assert request.extensions["timeout"]["read"] == 12.5


def test_a_session_without_a_project_sends_no_project_header() -> None:
    server = Server({("GET", "/chips"): [httpx.Response(200, json=CHIPS)]})
    server.session(project_id=None).api.chip.list_chips()

    assert "X-Project-Id" not in server.requests[0].headers


def test_a_request_option_overrides_the_project_for_one_call() -> None:
    server = Server({("GET", "/chips"): [httpx.Response(200, json=CHIPS)]})
    qdash = server.session()
    qdash.api.chip.list_chips(request_options={"additional_headers": {"X-Project-Id": "other"}})
    qdash.api.chip.list_chips()

    assert [r.headers.get_list("X-Project-Id") for r in server.requests] == [
        ["other"],
        ["project-a"],
    ]


def test_path_parameters_are_percent_encoded() -> None:
    server = Server()
    with pytest.raises(ApiError):
        server.session().api.execution.get_execution("a/../b")

    assert server.requests[0].url.raw_path == b"/executions/a%2F..%2Fb"


@pytest.mark.parametrize(
    ("status", "raised"),
    [(404, ApiError), (422, UnprocessableEntityError), (500, ApiError)],
)
def test_generated_resources_raise_api_errors_once(status: int, raised: type[ApiError]) -> None:
    server = Server({("GET", "/chips"): [httpx.Response(status, json={"detail": "boom"})]})
    with pytest.raises(raised) as error:
        server.session().api.chip.list_chips()

    assert error.value.status_code == status
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    ("status", "raised"),
    [
        (401, QDashAuthError),
        (403, QDashAuthError),
        (404, QDashNotFoundError),
        (409, QDashConflictError),
        (422, QDashValidationError),
        (500, QDashApiError),
        (503, QDashApiError),
    ],
)
def test_helpers_map_statuses_to_sdk_errors(status: int, raised: type[QDashApiError]) -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/validate"): [
                httpx.Response(status, json={"detail": "x"})
            ]
        }
    )
    with pytest.raises(raised) as error:
        server.session().pipelines.validate(pipeline(), chip_id=CHIP)

    assert type(error.value) is raised
    assert isinstance(error.value, ApiError)
    assert error.value.status_code == status
    assert error.value.payload == {"detail": "x"}
    assert str(error.value) == f"{status}: x"


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504])
def test_execute_is_sent_once_after_an_error_status(status: int) -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [
                httpx.Response(status, headers={"Retry-After": "0"}, json={"detail": "busy"}),
                httpx.Response(202, json=execute_body()),
            ]
        }
    )
    with pytest.raises(QDashApiError):
        server.session().pipelines.execute(pipeline(), chip_id=CHIP)

    assert server.paths() == [("POST", "/calibration-pipelines/execute")]


def test_writes_are_sent_once_after_a_read_timeout() -> None:
    requests: list[httpx.Request] = []

    def timeout(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    config = QDashConfig(base_url="http://qdash.local", api_token="t", project_id="p")
    http_client = httpx.Client(transport=httpx.MockTransport(timeout))
    qdash = QDash(config, http_client=http_client)
    with pytest.raises(QDashTransportError):
        qdash.pipelines.execute(pipeline(), chip_id=CHIP)
    with pytest.raises(QDashTransportError):
        qdash.workflows.run("check_t1")
    with pytest.raises(httpx.ReadTimeout):
        qdash.api.flow.execute_flow("check_t1", parameters={})

    assert [r.url.path for r in requests] == [
        "/calibration-pipelines/execute",
        "/flows/check_t1/execute",
        "/flows/check_t1/execute",
    ]


def test_generated_writes_are_not_retried_by_default() -> None:
    server = Server(
        {
            ("POST", "/flows/check_t1/execute"): [
                httpx.Response(503, headers={"Retry-After": "0"}),
                httpx.Response(200, json=execute_body()),
            ]
        }
    )
    with pytest.raises(ApiError):
        server.session().api.flow.execute_flow("check_t1", parameters={})

    assert len(server.requests) == 1


def test_helper_reads_retry_transient_statuses_within_read_attempts() -> None:
    server = Server(
        {
            ("GET", "/flows"): [
                httpx.Response(503, headers={"retry-after-ms": "1"}),
                httpx.Response(503, headers={"retry-after-ms": "1"}),
                httpx.Response(200, json={"flows": []}),
            ]
        }
    )
    assert server.session().workflows.list() == []
    assert len(server.requests) == 3

    server = Server({("GET", "/flows"): [httpx.Response(503, headers={"retry-after-ms": "1"})]})
    config = server.config().model_copy(update={"read_attempts": 1})
    with pytest.raises(QDashApiError):
        QDash(config, http_client=server.http_client()).workflows.list()
    assert len(server.requests) == 1


def test_a_response_that_does_not_parse_is_a_transport_error() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json={"x": 1})]}
    )
    with pytest.raises(QDashTransportError, match="did not match the API schema"):
        server.session().pipelines.validate(pipeline(), chip_id=CHIP)


def test_responses_keep_fields_a_newer_server_adds() -> None:
    body = {**validate_body(), "added_later": {"x": 1}}
    server = Server({("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=body)]})
    result = server.session().pipelines.validate(pipeline(), chip_id=CHIP)

    assert result.valid is True
    assert result.model_extra == {"added_later": {"x": 1}}


def test_login_mode_signs_in_once_and_uses_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_TEST_PASSWORD", "secret")
    server = Server(
        {
            ("POST", "/auth/login"): [httpx.Response(200, json={"access_token": "login-token"})],
            ("GET", "/chips"): [httpx.Response(200, json=CHIPS)],
        }
    )
    config = QDashConfig(
        base_url="http://qdash.local", username="alice", password_env="QDASH_TEST_PASSWORD"
    )
    qdash = QDash(config, http_client=server.http_client())
    assert server.requests == []
    qdash.api.chip.list_chips()
    qdash.api.chip.list_chips()

    assert server.paths() == [("POST", "/auth/login"), ("GET", "/chips"), ("GET", "/chips")]
    assert server.requests[0].content == b"username=alice&password=secret"
    assert [r.headers["Authorization"] for r in server.requests[1:]] == ["Bearer login-token"] * 2


def test_failed_login_raises_an_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_TEST_PASSWORD", "wrong")
    server = Server({("POST", "/auth/login"): [httpx.Response(401, json={"detail": "bad"})]})
    config = QDashConfig(
        base_url="http://qdash.local", username="alice", password_env="QDASH_TEST_PASSWORD"
    )
    with pytest.raises(QDashAuthError):
        QDash(config, http_client=server.http_client()).workflows.list()
    assert server.paths() == [("POST", "/auth/login")]


def test_a_session_needs_credentials() -> None:
    with pytest.raises(QDashConfigError, match="QDASH_API_TOKEN"):
        QDash(QDashConfig(base_url="http://qdash.local"))


def test_from_env_reads_the_client_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "QDASH_BASE_URL": "https://qdash.example/api/",
        "QDASH_API_TOKEN": "tok",
        "QDASH_PROJECT_ID": "proj",
        "QDASH_CF_ACCESS_CLIENT_ID": "cf-id",
        "QDASH_CF_ACCESS_CLIENT_SECRET": "cf-secret",
        "QDASH_TIMEOUT_SECONDS": "7",
        "QDASH_VERIFY_TLS": "false",
        "QDASH_PROXY": "http://proxy.local:3128",
        "QDASH_USER_AGENT": "agent/2",
        "QDASH_RETRY_MAX_ATTEMPTS": "5",
    }.items():
        monkeypatch.setenv(name, value)

    config = QDashConfig.from_env()

    assert config.base_url == "https://qdash.example/api"
    assert (config.api_token, config.project_id) == ("tok", "proj")
    assert (config.cf_access_client_id, config.cf_access_client_secret) == ("cf-id", "cf-secret")
    assert (config.timeout_sec, config.verify_tls) == (7.0, False)
    assert (config.proxy, config.user_agent, config.read_attempts) == (
        "http://proxy.local:3128",
        "agent/2",
        5,
    )


def test_from_env_needs_a_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QDASH_BASE_URL", raising=False)
    with pytest.raises(QDashConfigError, match="QDASH_BASE_URL"):
        QDashConfig.from_env()


def test_from_file_reads_a_client_profile(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_text(
        "[default]\nbase_url = http://default.local\napi_token = d\n\n"
        "[lab]\nbase_url = http://lab.local/\napi_token = lab-token\nproject_id = lab\n"
        "timeout_seconds = 9\nverify_tls = false\nmax_workers = 4\nretry_max_attempts = 2\n"
        "retry_backoff_seconds = 0.5\n",
        encoding="utf-8",
    )

    config = QDashConfig.from_file("lab", path)

    assert (config.base_url, config.api_token, config.project_id) == (
        "http://lab.local",
        "lab-token",
        "lab",
    )
    assert (config.timeout_sec, config.verify_tls, config.read_attempts) == (9.0, False, 2)
    with pytest.raises(QDashConfigError, match="profile not found"):
        QDashConfig.from_file("missing", path)
    with pytest.raises(QDashConfigError, match="not found"):
        QDashConfig.from_file("lab", tmp_path / "absent.ini")


def test_from_profile_owns_a_client_with_the_configured_transport(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_text(
        "[lab]\nbase_url = http://lab.local\napi_token = t\nproject_id = lab\n"
        "timeout_seconds = 4\nproxy = http://proxy.local:3128\nverify_tls = false\n",
        encoding="utf-8",
    )
    with QDash.from_profile("lab", path, project_id="other") as qdash:
        http_client = qdash._http_client
        assert qdash.project_id == "other"
        assert http_client.timeout.read == 4.0
        mounts: list[Any] = list(http_client._mounts.values())
        assert [mount._pool._proxy_url.host for mount in mounts] == [b"proxy.local"]
        transport: Any = http_client._transport
        assert transport._pool._ssl_context.verify_mode == ssl.CERT_NONE
    assert http_client.is_closed


def test_validate_body_is_the_strict_spec() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    server.session().pipelines.validate(pipeline(), chip_id=CHIP)

    assert json.loads(server.requests[0].content) == {"chip_id": CHIP, "spec": pipeline().to_spec()}


def test_run_reattaches_to_a_dispatched_execution() -> None:
    from test_sdk_session import detail

    server = Server(
        {
            ("GET", "/executions/exec-9"): [
                httpx.Response(404, json={"detail": "not yet"}),
                httpx.Response(200, json=detail("failed", "failed")),
            ]
        }
    )
    qdash = server.session()
    run = qdash.run("exec-9")
    assert server.requests == []

    result = run.wait(timeout_seconds=10, poll_interval_seconds=3)

    assert (result.execution_id, result.status) == ("exec-9", "failed")
    assert server.sleeps == [3]
    with pytest.raises(ValueError, match="execution_id"):
        qdash.run("")


@pytest.mark.parametrize(
    ("route", "save"),
    [
        (
            ("PATCH", "/dashboards/d-1"),
            lambda q: q.dashboards.update("d-1", Dashboard("d"), expected_version=3),
        ),
        (
            ("PATCH", "/metric-scripts/s-1"),
            lambda q: q.scripts.update("s-1", Script(name="s", source="x"), expected_revision=2),
        ),
    ],
)
def test_a_stale_save_raises_a_conflict_without_retry(route: tuple[str, str], save: Any) -> None:
    server = Server({route: [httpx.Response(409, json={"detail": "changed since version 3"})]})
    with pytest.raises(QDashConflictError, match="changed since"):
        save(server.session())

    assert server.paths() == [route]
    sent = json.loads(server.requests[0].content)
    assert sent.get("expected_version", sent.get("expected_revision")) in (2, 3)


def test_a_workflow_run_without_its_recorded_echo_is_unknown_and_not_retried() -> None:
    # A server that predates run recording starts the flow but echoes no run.
    server = Server(
        {("POST", "/flows/check_t1/execute"): [httpx.Response(200, json=execute_body())]}
    )
    with pytest.raises(RuntimeError, match="Workflow result unknown"):
        server.session().workflows.run("check_t1", idempotency_key="k-1")

    assert len(server.requests) == 1


def test_a_pipeline_run_outside_its_session_is_unknown_and_not_retried() -> None:
    from test_sdk_session import calibration_session_body

    server = Server(
        {
            ("GET", "/calibration-sessions/cs-1"): [
                httpx.Response(200, json=calibration_session_body())
            ],
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
        }
    )
    with pytest.raises(RuntimeError, match="Pipeline result unknown"):
        server.session().pipelines.execute(pipeline(), chip_id=CHIP, calibration_session_id="cs-1")

    assert server.paths().count(("POST", "/calibration-pipelines/execute")) == 1


def test_a_session_on_another_chip_dispatches_nothing() -> None:
    from test_sdk_session import calibration_session_body

    server = Server(
        {
            ("GET", "/calibration-sessions/cs-1"): [
                httpx.Response(200, json=calibration_session_body(chip_id="other"))
            ]
        }
    )
    with pytest.raises(ValueError, match="preflight failed"):
        server.session().pipelines.execute(pipeline(), chip_id=CHIP, calibration_session_id="cs-1")

    assert server.paths() == [("GET", "/calibration-sessions/cs-1")]


def test_the_sdk_imports_nothing_from_qdash_client() -> None:
    import subprocess
    import sys

    script = (
        "import sys\n"
        "import qdash.sdk, qdash.sdk.types, qdash.sdk.calibration, qdash.sdk.dashboard\n"
        "from qdash.sdk import QDash, QDashConfig\n"
        "QDash(QDashConfig(base_url='http://qdash.invalid', api_token='t')).close()\n"
        "print(sorted(m for m in sys.modules if m.startswith('qdash.client')))\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
