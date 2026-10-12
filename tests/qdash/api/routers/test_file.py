"""The file routes read server files, so they need a user and stay inside their trees."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from qdash.api.services.task_result_service import TaskResultService
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument


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
def knowledge(tmp_path: Path, test_client: TestClient):
    """A knowledge workspace with one task folder holding its plot."""
    from qdash.api.dependencies import get_knowledge_file_service
    from qdash.api.services.file_service import FileService

    task = tmp_path / "knowledge" / "one_qubit_coarse" / "CheckRabi"
    task.mkdir(parents=True)
    (task / "index.md").write_text("![Rabi](./check_rabi_expected_1.png)\n")
    (task / "check_rabi_expected_1.png").write_bytes(b"\x89PNG-rabi")
    (task / "notes.svg").write_text("<svg><script>alert(1)</script></svg>")
    app = test_client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_knowledge_file_service] = lambda: FileService(
        tmp_path / "knowledge", label="knowledge"
    )
    yield tmp_path / "knowledge"
    app.dependency_overrides.pop(get_knowledge_file_service, None)


def test_a_knowledge_image_is_served_for_the_markdown_preview(
    test_client: TestClient, headers: dict[str, str], knowledge: Path
) -> None:
    response = test_client.get(
        "/knowledge/files/image",
        params={"path": "one_qubit_coarse/CheckRabi/check_rabi_expected_1.png"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"\x89PNG-rabi"


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("one_qubit_coarse/CheckRabi/index.md", 400),
        ("one_qubit_coarse/CheckRabi/notes.svg", 400),
        ("one_qubit_coarse/CheckRabi/missing.png", 404),
        ("../outside.png", 400),
    ],
)
def test_only_raster_images_inside_the_workspace_are_served(
    test_client: TestClient,
    headers: dict[str, str],
    knowledge: Path,
    path: str,
    status: int,
) -> None:
    (knowledge.parent / "outside.png").write_bytes(b"TOP-SECRET-CONTENT")

    response = test_client.get("/knowledge/files/image", params={"path": path}, headers=headers)

    assert response.status_code == status
    assert b"TOP-SECRET-CONTENT" not in response.content


def test_knowledge_images_require_a_signed_in_user(
    test_client: TestClient, knowledge: Path
) -> None:
    response = test_client.get(
        "/knowledge/files/image",
        params={"path": "one_qubit_coarse/CheckRabi/check_rabi_expected_1.png"},
    )

    assert response.status_code in {401, 403}
