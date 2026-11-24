"""Regression checks for authentication bodies and safe-read protocol failures."""

import httpx
import pytest

from qdash.sdk import QDash, QDashApiError, QDashConfig


@pytest.mark.parametrize("content", [b"[]", b"null", b"not-json", b"", b'"text"'])
def test_invalid_login_response_raises_sdk_error(
    content: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QDASH_TEST_LOGIN_PASSWORD", "test-password")
    config = QDashConfig(
        base_url="http://qdash.local", username="user", password_env="QDASH_TEST_LOGIN_PASSWORD"
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content))
    ) as client:
        session = QDash(config, http_client=client)
        with pytest.raises(QDashApiError, match="Login response"):
            session.api.chip.list_chips()


def test_helper_read_retries_remote_protocol_error_but_write_does_not() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST" or len(requests) == 1:
            raise httpx.RemoteProtocolError("disconnected", request=request)
        return httpx.Response(200, json={"flows": []})

    config = QDashConfig(base_url="http://qdash.local", api_token="test", project_id="p")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        session = QDash(config, http_client=client)
        assert session.workflows.list() == []
        assert len(requests) == 2
        with pytest.raises(QDashApiError):
            session.workflows.run("coherence_check")
        assert len(requests) == 3


def test_config_mutations_do_not_change_session_scope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"chips": [], "total": 0})

    config = QDashConfig(base_url="http://qdash.local", api_token="test", project_id="original")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        session = QDash(config, http_client=client)
        config.project_id = "changed-input"
        session.config.project_id = "changed-copy"
        session.api.chip.list_chips()
        assert session.project_id == "original"
        assert session.config.project_id == "original"
        assert requests[-1].headers["X-Project-Id"] == session.project_id
        other = session.with_project("other")
        other.api.chip.list_chips()
        assert requests[-1].headers["X-Project-Id"] == other.project_id == "other"
        assert session.project_id == "original"
