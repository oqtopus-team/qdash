"""Tests for execution router endpoints."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pymongo.database import Database as PyMongoDatabase

from qdash.common.raw_data import PreFitRawData
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


@pytest.fixture
def test_project(init_db: PyMongoDatabase[Any]) -> ProjectDocument:
    """Create a test project with owner membership."""
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_user_id=user.user_id,
        owner_username="test_user",
    )
    project.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="test_user",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="test_user",
    )
    membership.insert()

    return project


@pytest.fixture
def viewer_user(init_db: PyMongoDatabase[Any]) -> UserDocument:
    """Create a viewer user (non-owner)."""
    user = UserDocument(
        username="viewer_user",
        hashed_password="hashed",
        access_token="viewer_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="viewer_user",
        role=ProjectRole.VIEWER,
        status="active",
        invited_by="test_user",
    )
    membership.insert()

    return user


@pytest.fixture
def editor_user(init_db: PyMongoDatabase[Any]) -> UserDocument:
    """Create an editor user."""
    user = UserDocument(
        username="editor_user",
        hashed_password="hashed",
        access_token="editor_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="editor_user",
        role=ProjectRole.EDITOR,
        status="active",
        invited_by="test_user",
    )
    membership.insert()

    return user


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Owner authentication headers."""
    return {
        "Authorization": "Bearer test_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def viewer_headers() -> dict[str, str]:
    """Viewer authentication headers."""
    return {
        "Authorization": "Bearer viewer_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def editor_headers() -> dict[str, str]:
    """Editor authentication headers."""
    return {
        "Authorization": "Bearer editor_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def sample_execution(test_project: ProjectDocument) -> ExecutionHistoryDocument:
    """Create a sample execution history document."""
    execution = ExecutionHistoryDocument(
        project_id="test_project",
        execution_id="exec-001",
        name="test_flow",
        status="completed",
        chip_id="chip-1",
        username="test_user",
        tags=["test"],
        note={},
        calib_data_path="/tmp/calib",
        message="completed",
        system_info=SystemInfoModel(),
        start_at=datetime.now(tz=timezone.utc),
        end_at=datetime.now(tz=timezone.utc),
        elapsed_time=10.0,
    )
    execution.insert()
    return execution


CANCEL_FLOW_RUN_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _seed_execution(
    *,
    execution_id: str,
    status: str,
    start_at: datetime | None,
    chip_id: str = "chip-1",
) -> None:
    ExecutionHistoryDocument(
        project_id="test_project",
        username="test_user",
        name="flow",
        execution_id=execution_id,
        calib_data_path="/tmp/calib",
        note={},
        status=status,
        tags=[],
        chip_id=chip_id,
        start_at=start_at,
        message="",
        system_info=SystemInfoModel(),
    ).insert()


class TestExecutionActivity:
    """GET /executions/activity buckets a chip's executions per calendar day."""

    def test_counts_per_day_by_status_with_empty_days(
        self, test_client, test_project, auth_headers
    ) -> None:
        zone = ZoneInfo("Asia/Tokyo")
        today = datetime.now(tz=zone).replace(hour=12, minute=0, second=0, microsecond=0)
        _seed_execution(execution_id="e-1", status="completed", start_at=today)
        _seed_execution(execution_id="e-2", status="completed", start_at=today)
        _seed_execution(execution_id="e-3", status="failed", start_at=today - timedelta(days=1))
        _seed_execution(execution_id="e-4", status="cancelling", start_at=today)
        _seed_execution(execution_id="e-5", status="pending", start_at=today)
        _seed_execution(execution_id="old", status="completed", start_at=today - timedelta(days=40))
        _seed_execution(execution_id="other-chip", status="failed", start_at=today, chip_id="x")
        _seed_execution(execution_id="unstarted", status="scheduled", start_at=None)

        response = test_client.get(
            "/executions/activity",
            params={"chip_id": "chip-1", "days": 7, "timezone": "Asia/Tokyo"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["chip_id"] == "chip-1"
        assert body["days"] == 7
        assert body["timezone"] == "Asia/Tokyo"
        assert len(body["buckets"]) == 7
        assert body["until"] == today.date().isoformat()
        assert body["buckets"][-1]["date"] == body["until"]
        assert body["buckets"][0]["date"] == body["since"]
        last = body["buckets"][-1]
        assert last == {
            "date": today.date().isoformat(),
            "completed": 2,
            "failed": 0,
            "running": 1,
            "scheduled": 1,
            "cancelled": 0,
            "other": 0,
            "total": 4,
        }
        yesterday = body["buckets"][-2]
        assert yesterday["failed"] == 1 and yesterday["total"] == 1
        assert all(bucket["total"] == 0 for bucket in body["buckets"][:-2])

    def test_days_follow_the_requested_time_zone(
        self, test_client, test_project, auth_headers
    ) -> None:
        """An execution late in the UTC evening belongs to the next day in Tokyo."""
        utc_today = datetime.now(tz=timezone.utc).date()
        late_utc = datetime.combine(utc_today, datetime.min.time(), tzinfo=timezone.utc).replace(
            hour=22
        )
        _seed_execution(execution_id="late", status="completed", start_at=late_utc)

        in_utc = test_client.get(
            "/executions/activity",
            params={"chip_id": "chip-1", "days": 3, "timezone": "UTC"},
            headers=auth_headers,
        ).json()
        in_tokyo = test_client.get(
            "/executions/activity",
            params={"chip_id": "chip-1", "days": 3, "timezone": "Asia/Tokyo"},
            headers=auth_headers,
        ).json()

        utc_day = next(b for b in in_utc["buckets"] if b["total"] == 1)["date"]
        tokyo_days = [b["date"] for b in in_tokyo["buckets"] if b["total"] == 1]
        expected_tokyo = late_utc.astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat()
        assert utc_day == utc_today.isoformat()
        # The Tokyo day is tomorrow in UTC terms; it is inside the window only when the
        # Tokyo calendar has already reached it, which is exactly what the API reports.
        assert tokyo_days in ([expected_tokyo], [])

    def test_rejects_an_unknown_time_zone(self, test_client, test_project, auth_headers) -> None:
        response = test_client.get(
            "/executions/activity",
            params={"chip_id": "chip-1", "timezone": "Mars/Olympus"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Unknown time zone" in response.json()["detail"]


def test_get_execution_lock_status_includes_latest_execution(
    test_client: TestClient,
    test_project: ProjectDocument,
    auth_headers: dict[str, str],
) -> None:
    execution = ExecutionHistoryDocument(
        project_id=test_project.project_id,
        execution_id="exec-running",
        name="quick-run:CheckChevron",
        status="running",
        chip_id="chip-1",
        username="test_user",
        tags=[],
        note={},
        calib_data_path="/tmp/calib",
        message="running",
        system_info=SystemInfoModel(),
        start_at=datetime.now(tz=timezone.utc),
    )
    execution.insert()
    ExecutionLockDocument.lock(test_project.project_id)

    response = test_client.get("/executions/lock-status", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "lock": True,
        "execution_id": "exec-running",
        "chip_id": "chip-1",
        "name": "quick-run:CheckChevron",
        "status": "running",
    }


@pytest.fixture
def calib_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Serve ``tmp_path`` as the calibration data tree."""
    monkeypatch.setenv("CALIB_DATA_PATH", str(tmp_path))
    return tmp_path


def test_get_figure_by_path_maps_container_calib_data_path(
    test_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Serve figures stored under the container calib-data mount from host API mode."""
    local_base = tmp_path / "calib_data"
    figure = local_base / "proj-1" / "figure.png"
    figure.parent.mkdir(parents=True)
    figure.write_bytes(b"png")
    monkeypatch.setenv("CALIB_DATA_PATH", str(local_base))

    response = test_client.get(
        "/executions/figure",
        params={"path": "/app/calib_data/proj-1/figure.png"},
    )

    assert response.status_code == 200
    assert response.content == b"png"


def test_download_artifact_by_path(
    test_client: TestClient,
    calib_data: Path,
) -> None:
    tmp_path = calib_data
    artifact = tmp_path / "raw_data.nc"
    artifact.write_bytes(b"netcdf")

    response = test_client.get("/executions/artifact", params={"path": str(artifact)})

    assert response.status_code == 200
    assert response.content == b"netcdf"
    assert response.headers["content-disposition"] == 'attachment; filename="raw_data.nc"'


def test_download_artifacts_as_archive(
    test_client: TestClient,
    calib_data: Path,
) -> None:
    tmp_path = calib_data
    figure_dir = tmp_path / "figures"
    raw_dir = tmp_path / "raw"
    figure_dir.mkdir()
    raw_dir.mkdir()
    figure = figure_dir / "artifact.json"
    raw_data = raw_dir / "artifact.json"
    figure.write_text('{"data": []}')
    raw_data.write_text("raw")

    response = test_client.get(
        "/executions/artifacts/archive",
        params=[("paths", str(figure)), ("paths", str(raw_data))],
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="artifacts.zip"'
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.namelist() == ["artifact.json", "artifact_2.json"]
        assert archive.read("artifact.json") == b'{"data": []}'
        assert archive.read("artifact_2.json") == b"raw"


def test_preview_artifact_by_path_returns_complex_table(
    test_client: TestClient,
    calib_data: Path,
) -> None:
    tmp_path = calib_data
    artifact = tmp_path / "raw_data.nc"
    PreFitRawData(
        target="Q00",
        data=np.array([1 + 2j, 3 + 4j]),
        axes={"sweep_range": np.array([10.0, 20.0])},
        source_type="test.SweepData",
    ).save_netcdf(artifact)

    response = test_client.get("/executions/artifact/preview", params={"path": str(artifact)})

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "raw_data.nc"
    assert body["target"] == "Q00"
    assert body["source_type"] == "test.SweepData"
    assert body["shape"] == [2]
    assert body["dtype"] == "complex"
    assert body["columns"] == ["sweep_range", "real", "imag", "abs"]
    assert body["rows"] == [
        {"sweep_range": 10.0, "real": 1.0, "imag": 2.0, "abs": pytest.approx(5**0.5)},
        {"sweep_range": 20.0, "real": 3.0, "imag": 4.0, "abs": 5.0},
    ]
    assert body["total_rows"] == 2
    assert body["truncated"] is False


def test_preview_artifact_by_path_rejects_non_netcdf(
    test_client: TestClient,
    calib_data: Path,
) -> None:
    tmp_path = calib_data
    artifact = tmp_path / "figure.json"
    artifact.write_text("{}")

    response = test_client.get("/executions/artifact/preview", params={"path": str(artifact)})

    assert response.status_code == 400


@pytest.mark.parametrize(
    "endpoint",
    ["/executions/figure", "/executions/artifact", "/executions/artifact/preview"],
)
@pytest.mark.parametrize("escape", ["absolute", "traversal", "symlink"])
def test_calibration_file_endpoints_serve_nothing_outside_calib_data(
    test_client: TestClient,
    calib_data: Path,
    tmp_path_factory: pytest.TempPathFactory,
    endpoint: str,
    escape: str,
) -> None:
    """These endpoints take no token, so a path must not reach other server files."""
    secret = tmp_path_factory.mktemp("outside") / "secret.nc"
    secret.write_bytes(b"TOP-SECRET-CONTENT")
    if escape == "absolute":
        path = str(secret)
    elif escape == "traversal":
        path = f"{calib_data}/../{secret.parent.name}/secret.nc"
        (calib_data.parent / secret.parent.name).mkdir(exist_ok=True)
        (calib_data.parent / secret.parent.name / "secret.nc").write_bytes(b"TOP-SECRET-CONTENT")
    else:
        link = calib_data / "link.nc"
        link.symlink_to(secret)
        path = str(link)

    response = test_client.get(endpoint, params={"path": path})

    assert response.status_code == 404
    assert b"TOP-SECRET-CONTENT" not in response.content


def test_artifact_archive_refuses_a_path_outside_calib_data(
    test_client: TestClient,
    calib_data: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    inside = calib_data / "figure.json"
    inside.write_text("{}")
    secret = tmp_path_factory.mktemp("outside") / "secret.txt"
    secret.write_text("secret")

    response = test_client.get(
        "/executions/artifacts/archive",
        params=[("paths", str(inside)), ("paths", str(secret))],
    )

    assert response.status_code == 404


class TestCancelExecution:
    """Tests for POST /executions/{flow_run_id}/cancel endpoint."""

    def test_cancel_success(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test successful cancellation of a running execution."""
        mock_state = MagicMock()
        mock_state.type.value = "RUNNING"

        mock_flow_run = MagicMock()
        mock_flow_run.state = mock_state
        mock_flow_run.parameters = {"project_id": "test_project"}

        mock_client = MagicMock()
        mock_client.read_flow_run = AsyncMock(return_value=mock_flow_run)
        mock_client.set_flow_run_state = AsyncMock(return_value=None)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.execution_service.get_client", return_value=async_cm):
            response = test_client.post(
                f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == CANCEL_FLOW_RUN_ID
        assert data["status"] == "cancelling"

    def test_cancel_success_marks_execution_cancelling(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """A successful cancellation marks the matching execution cancelling in Mongo."""
        execution = ExecutionHistoryDocument(
            project_id="test_project",
            execution_id="exec-cancel",
            name="test_flow",
            status="running",
            chip_id="chip-1",
            username="test_user",
            tags=["test"],
            note={"flow_run_id": CANCEL_FLOW_RUN_ID},
            calib_data_path="/tmp/calib",
            message="running",
            system_info=SystemInfoModel(),
            start_at=datetime.now(tz=timezone.utc),
        )
        execution.insert()

        mock_state = MagicMock()
        mock_state.type.value = "RUNNING"

        mock_flow_run = MagicMock()
        mock_flow_run.state = mock_state
        mock_flow_run.parameters = {"project_id": "test_project"}

        mock_client = MagicMock()
        mock_client.read_flow_run = AsyncMock(return_value=mock_flow_run)
        mock_client.set_flow_run_state = AsyncMock(return_value=None)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.execution_service.get_client", return_value=async_cm):
            response = test_client.post(
                f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
                headers=auth_headers,
            )

        assert response.status_code == 200
        reloaded = ExecutionHistoryDocument.find_one(
            {"project_id": "test_project", "execution_id": "exec-cancel"}
        ).run()
        assert reloaded is not None
        assert reloaded.status == "cancelling"

    def test_cancel_success_returns_200_when_marking_cancelling_fails(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Prefect already accepted the cancellation, so a failed cancelling write still returns 200."""
        mock_state = MagicMock()
        mock_state.type.value = "RUNNING"

        mock_flow_run = MagicMock()
        mock_flow_run.state = mock_state
        mock_flow_run.parameters = {"project_id": "test_project"}

        mock_client = MagicMock()
        mock_client.read_flow_run = AsyncMock(return_value=mock_flow_run)
        mock_client.set_flow_run_state = AsyncMock(return_value=None)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("qdash.api.services.execution_service.get_client", return_value=async_cm),
            patch(
                "qdash.api.services.execution_service.mark_executions_cancelling_by_flow_run_id",
                side_effect=RuntimeError("boom"),
            ),
        ):
            response = test_client.post(
                f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelling"

    def test_cancel_invalid_uuid_returns_400(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test cancelling with non-UUID returns 400."""
        response = test_client.post(
            "/executions/not-a-uuid/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Invalid flow run ID" in response.json()["detail"]

    def test_cancel_wrong_project_returns_403(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test cancelling a flow run from another project returns 403."""
        mock_state = MagicMock()
        mock_state.type.value = "RUNNING"

        mock_flow_run = MagicMock()
        mock_flow_run.state = mock_state
        mock_flow_run.parameters = {"project_id": "other_project"}

        mock_client = MagicMock()
        mock_client.read_flow_run = AsyncMock(return_value=mock_flow_run)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.execution_service.get_client", return_value=async_cm):
            response = test_client.post(
                f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
                headers=auth_headers,
            )

        assert response.status_code == 403

    def test_cancel_completed_execution_returns_409(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test cancelling a completed execution returns 409."""
        mock_state = MagicMock()
        mock_state.type.value = "COMPLETED"

        mock_flow_run = MagicMock()
        mock_flow_run.state = mock_state
        mock_flow_run.parameters = {"project_id": "test_project"}

        mock_client = MagicMock()
        mock_client.read_flow_run = AsyncMock(return_value=mock_flow_run)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.execution_service.get_client", return_value=async_cm):
            response = test_client.post(
                f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
                headers=auth_headers,
            )

        assert response.status_code == 409
        assert "cannot be cancelled" in response.json()["detail"]

    def test_cancel_requires_authentication(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
    ) -> None:
        """Test cancellation without auth returns 401."""
        response = test_client.post(
            f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
        )
        assert response.status_code == 401


class TestListExecutions:
    """Tests for GET /executions endpoint."""

    def test_list_executions_empty(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test listing executions when none exist."""
        response = test_client.get(
            "/executions",
            headers=auth_headers,
            params={"chip_id": "chip-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["executions"] == []
        assert data["total"] == 0

    def test_list_executions_with_data(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
        sample_execution: ExecutionHistoryDocument,
    ) -> None:
        """Test listing executions returns data."""
        response = test_client.get(
            "/executions",
            headers=auth_headers,
            params={"chip_id": "chip-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["executions"]) == 1
        assert data["executions"][0]["execution_id"] == "exec-001"
        assert data["total"] == 1

    def test_list_executions_total_reflects_all_records(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that total reflects all records even when pagination limits results."""
        now = datetime.now(tz=timezone.utc)
        for i in range(3):
            execution = ExecutionHistoryDocument(
                project_id="test_project",
                execution_id=f"exec-multi-{i:03d}",
                name="test_flow",
                status="completed",
                chip_id="chip-1",
                username="test_user",
                tags=["test"],
                note={},
                calib_data_path="/tmp/calib",
                message="completed",
                system_info=SystemInfoModel(),
                start_at=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
                end_at=now,
                elapsed_time=10.0,
            )
            execution.insert()

        response = test_client.get(
            "/executions",
            headers=auth_headers,
            params={"chip_id": "chip-1", "skip": 2, "limit": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["executions"]) == 1
        assert data["total"] == 3


class TestGetExecution:
    """Tests for GET /executions/{execution_id} endpoint."""

    def test_get_execution_by_prefect_flow_run_id(
        self,
        test_client: TestClient,
        sample_execution: ExecutionHistoryDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Resolve a dispatched Prefect flow run to its QDash execution."""
        sample_execution.note = {"flow_run_id": "flow-run-001"}
        sample_execution.save()

        response = test_client.get(
            "/executions/flow-run-001",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["name"] == "test_flow-exec-001"

    def test_get_execution_not_found(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting non-existent execution returns 404."""
        response = test_client.get(
            "/executions/nonexistent",
            headers=auth_headers,
        )
        assert response.status_code == 404


def test_execution_availability_tracks_target_conflicts_without_creating_executions(
    test_client: TestClient,
    test_project: ProjectDocument,
    auth_headers: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.common import execution_resources
    from qdash.repository.execution_lock import MongoExecutionLockRepository

    wiring = tmp_path / "chip-1" / "config" / "wiring.yaml"
    wiring.parent.mkdir(parents=True)
    wiring.write_text(
        "chip-1:\n"
        "  - mux: 0\n    ctrl: [C0-1]\n    read_out: R0-1\n"
        "  - mux: 1\n    ctrl: [C1-1]\n    read_out: R1-1\n"
    )
    monkeypatch.setattr(execution_resources, "resolve_config_base_path", lambda: tmp_path)
    repo = MongoExecutionLockRepository()
    assert repo.try_lock(test_project.project_id, "running", "chip-1", ("mux:0",), False)
    before = list(ExecutionHistoryDocument.find_all().run())
    for chip, qid, available in [
        ("chip-1", "0", False),
        ("chip-1", "4", True),
        ("chip-2", "0", True),
    ]:
        response = test_client.post(
            "/executions/check-availability",
            headers=auth_headers,
            json={"parameters": {"chip_id": chip, "qid": qid}},
        )
        assert response.status_code == 200
        assert response.json()["available"] is available
        assert bool(response.json()["reason"]) is not available
    assert list(ExecutionHistoryDocument.find_all().run()) == before
    repo.unlock(test_project.project_id, "running")
    response = test_client.post(
        "/executions/check-availability",
        headers=auth_headers,
        json={"parameters": {"chip_id": "chip-1", "qid": "0"}},
    )
    assert response.json()["available"] is True


def test_execution_availability_requires_authentication(test_client: TestClient) -> None:
    response = test_client.post(
        "/executions/check-availability", json={"parameters": {"chip_id": "chip-1", "qid": "0"}}
    )
    assert response.status_code in (401, 403)
