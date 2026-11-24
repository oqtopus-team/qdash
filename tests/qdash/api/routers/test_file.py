"""The file routes read server files, so they need a user and stay inside their trees."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from qdash.api.services.task_result_service import TaskResultService
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument
from tests.qdash.api._operation_errors import ERRORS_LOGGER, assert_operation_failure


@pytest.fixture
def headers(init_db: object) -> dict[str, str]:
    UserDocument(
        username="alice",
        hashed_password="hashed",
        access_token="alice-token",
        system_info=SystemInfoModel(),
    ).insert()
    return {"Authorization": "Bearer alice-token"}


@pytest.fixture
def calib_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CALIB_DATA_PATH", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize(
    "path",
    ["/files/raw-data?path=/etc/hostname", "/config/files/tree", "/config/files/git/status"],
)
def test_file_routes_require_a_signed_in_user(test_client: TestClient, path: str) -> None:
    assert test_client.get(path).status_code in {401, 403}


def test_raw_data_serves_calibration_data(
    test_client: TestClient, headers: dict[str, str], calib_data: Path
) -> None:
    data = calib_data / "exec-1" / "raw.nc"
    data.parent.mkdir()
    data.write_bytes(b"netcdf")

    response = test_client.get("/files/raw-data", params={"path": str(data)}, headers=headers)

    assert response.status_code == 200
    assert response.content == b"netcdf"


@pytest.mark.parametrize("escape", ["absolute", "traversal"])
def test_raw_data_serves_nothing_outside_calibration_data(
    test_client: TestClient,
    headers: dict[str, str],
    calib_data: Path,
    tmp_path_factory: pytest.TempPathFactory,
    escape: str,
) -> None:
    secret = tmp_path_factory.mktemp("outside") / "secret.txt"
    secret.write_bytes(b"TOP-SECRET-CONTENT")
    path = (
        str(secret) if escape == "absolute" else f"{calib_data}/../{secret.parent.name}/secret.txt"
    )
    if escape == "traversal":
        target = calib_data.parent / secret.parent.name / "secret.txt"
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b"TOP-SECRET-CONTENT")

    response = test_client.get("/files/raw-data", params={"path": path}, headers=headers)

    assert response.status_code == 404
    assert b"TOP-SECRET-CONTENT" not in response.content


def test_figure_archive_refuses_files_outside_calibration_data(
    calib_data: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    inside = calib_data / "figure.png"
    inside.write_bytes(b"png")
    secret = tmp_path_factory.mktemp("outside") / "secret.png"
    secret.write_bytes(b"TOP-SECRET-CONTENT")

    with pytest.raises(HTTPException) as exc_info:
        TaskResultService.create_figures_zip([str(inside), str(secret)], "figures.zip")

    assert exc_info.value.status_code == 400
    assert str(secret) in str(exc_info.value.detail)


@pytest.fixture
def config_workspace(tmp_path: Path) -> Iterator[Path]:
    """Serve the config file routes from a temporary workspace."""
    from qdash.api.dependencies import get_file_service
    from qdash.api.main import app
    from qdash.api.services.file_service import FileService

    workspace = tmp_path / "config"
    workspace.mkdir()
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_file_service] = lambda: FileService(config_base_path=workspace)
    try:
        yield workspace
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_unreadable_config_file_returns_code_message_and_logged_error_id(
    test_client: TestClient,
    headers: dict[str, str],
    config_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = config_workspace / "settings.yaml"
    target.write_text("a: 1\n", encoding="utf-8")
    secret = f"Permission denied: '{target}' token=ghp_SECRET"
    original = Path.read_text

    def read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == target:
            raise PermissionError(secret)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)

    with caplog.at_level(logging.ERROR, logger=ERRORS_LOGGER):
        response = test_client.get(
            "/config/files/content", params={"path": "settings.yaml"}, headers=headers
        )

    assert_operation_failure(
        response,
        caplog,
        code="file_read_failed",
        message="Failed to read the file",
        cause=PermissionError,
        hidden=(str(config_workspace), "ghp_SECRET", "Permission denied"),
    )


def test_unwritable_config_file_returns_code_message_and_logged_error_id(
    test_client: TestClient,
    headers: dict[str, str],
    config_workspace: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (config_workspace / "settings.yaml").mkdir()

    with caplog.at_level(logging.ERROR, logger=ERRORS_LOGGER):
        response = test_client.put(
            "/config/files/content",
            json={"path": "settings.yaml", "content": "a: 2\n"},
            headers=headers,
        )

    assert_operation_failure(
        response,
        caplog,
        code="file_save_failed",
        message="Failed to save the file",
        cause=IsADirectoryError,
        hidden=(str(config_workspace), "Errno"),
    )


def test_config_file_expected_errors_and_success_keep_their_payloads(
    test_client: TestClient, headers: dict[str, str], config_workspace: Path
) -> None:
    missing = test_client.get(
        "/config/files/content", params={"path": "missing.yaml"}, headers=headers
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "File not found: missing.yaml"}

    traversal = test_client.put(
        "/config/files/content", json={"path": "../outside.yaml", "content": ""}, headers=headers
    )
    assert traversal.status_code == 400
    assert traversal.json() == {"detail": "Path traversal detected"}

    (config_workspace / "binary.yaml").write_bytes(b"\xff\xfe\x00")
    binary = test_client.get(
        "/config/files/content", params={"path": "binary.yaml"}, headers=headers
    )
    assert binary.status_code == 400
    assert binary.json() == {"detail": "File is not a text file"}

    saved = test_client.put(
        "/config/files/content",
        json={"path": "settings.yaml", "content": "a: 2\n"},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json() == {"message": "File saved successfully", "path": "settings.yaml"}

    read = test_client.get(
        "/config/files/content", params={"path": "settings.yaml"}, headers=headers
    )
    assert read.status_code == 200
    assert read.json()["content"] == "a: 2\n"
