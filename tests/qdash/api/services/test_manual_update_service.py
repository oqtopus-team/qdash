from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import plotly.graph_objects as go
import plotly.io as pio
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from qdash.api.schemas.calibration import ManualParameterUpdateRequest
from qdash.api.services.manual_update_service import ManualUpdateService
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.coupling_history import CouplingHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.qubit_history import QubitHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument


@pytest.fixture(autouse=True)
def disable_config_push(monkeypatch):
    monkeypatch.setattr(
        "qdash.api.services.calibration_github_service.config_github_credentials_available",
        lambda: False,
    )


def _request(**overrides: Any) -> ManualParameterUpdateRequest:
    values: dict[str, Any] = {
        "chip_id": "16Q",
        "qid": "4",
        "source_task_id": "source-task",
        "parameters": {"readout_frequency": {"value": 10.123, "unit": "GHz"}},
    }
    values.update(overrides)
    return ManualParameterUpdateRequest(**values)


def _source(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "task_id": "source-task",
        "name": "CheckResonatorSpectroscopy",
        "chip_id": "16Q",
        "qid": "4",
        "output_parameter_names": ["readout_frequency", "optimal_power"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_validate_source_accepts_completed_spectroscopy_result() -> None:
    service = ManualUpdateService()
    source = _source(status="completed")

    with patch(
        "qdash.api.services.manual_update_service.TaskResultHistoryDocument.find_one"
    ) as find_one:
        find_one.return_value.run.return_value = source
        assert service._validate_source_task(_request(), "project") is source


def test_validate_source_accepts_failed_spectroscopy_result() -> None:
    service = ManualUpdateService()
    source = _source(status="failed")

    with patch(
        "qdash.api.services.manual_update_service.TaskResultHistoryDocument.find_one"
    ) as find_one:
        find_one.return_value.run.return_value = source
        assert service._validate_source_task(_request(), "project") is source


@pytest.mark.parametrize(
    ("source", "detail"),
    [
        (_source(name="CheckT1"), "not supported"),
        (_source(chip_id="other"), "does not match"),
        (_source(qid="5"), "does not match"),
    ],
)
def test_validate_source_rejects_unrelated_task(source: SimpleNamespace, detail: str) -> None:
    service = ManualUpdateService()

    with (
        patch(
            "qdash.api.services.manual_update_service.TaskResultHistoryDocument.find_one"
        ) as find_one,
        pytest.raises(HTTPException, match=detail),
    ):
        find_one.return_value.run.return_value = source
        service._validate_source_task(_request(), "project")


def test_validate_source_rejects_unknown_output_parameter() -> None:
    service = ManualUpdateService()

    with (
        patch(
            "qdash.api.services.manual_update_service.TaskResultHistoryDocument.find_one"
        ) as find_one,
        pytest.raises(HTTPException, match="Unknown source output parameter"),
    ):
        find_one.return_value.run.return_value = _source()
        service._validate_source_task(
            _request(parameters={"qubit_frequency": {"value": 5.0, "unit": "GHz"}}),
            "project",
        )


def test_correction_point_requires_source_task() -> None:
    with pytest.raises(ValidationError, match="source_task_id is required"):
        _request(source_task_id=None, correction_point={"x": 9.95, "y": -25.0})


def test_persistence_failure_does_not_update_calibration_and_removes_artifacts(
    tmp_path: Path,
    init_db: Any,
) -> None:
    png_path = tmp_path / "correction.png"
    json_path = tmp_path / "correction.json"
    png_path.touch()
    json_path.touch()

    qubit_repo = Mock()
    activity = SimpleNamespace(activity_id="activity", status="running", ended_at=None, save=Mock())
    activity_repo = Mock()
    activity_repo.create_activity.return_value = activity
    param_version_repo = Mock()
    param_version_repo.create_version.return_value = SimpleNamespace(entity_id="entity")
    param_version_repo.get_by_task.return_value = []
    relation_repo = Mock()
    service = ManualUpdateService(
        qubit_repo=qubit_repo,
        activity_repo=activity_repo,
        param_version_repo=param_version_repo,
        relation_repo=relation_repo,
    )

    with (
        patch(
            "qdash.api.services.manual_update_service.TaskResultHistoryDocument.find_one"
        ) as find_one,
        patch.object(
            service,
            "_save_correction_figure",
            return_value=([str(png_path)], [str(json_path)]),
        ),
        patch(
            "qdash.api.services.manual_update_service.TaskResultHistoryDocument.insert",
            side_effect=RuntimeError("persistence failed"),
        ),
        pytest.raises(RuntimeError, match="persistence failed"),
    ):
        find_one.return_value.run.return_value = _source(status="completed")
        service.update_parameters(_request(), "project", "tester")

    qubit_repo.update_calib_data.assert_not_called()
    assert activity.status == "failed"
    assert not png_path.exists()
    assert not json_path.exists()


def test_save_correction_figure_persists_marker_artifacts(tmp_path) -> None:
    figure_dir = tmp_path / "fig"
    figure_dir.mkdir()
    source_path = figure_dir / "source.json"
    go.Figure(go.Heatmap(x=[9.9, 10.0], y=[-30.0, -20.0], z=[[1, 2], [3, 4]])).write_json(
        source_path
    )
    request = _request(correction_point={"x": 9.95, "y": -25.0})

    png_paths, json_paths = ManualUpdateService._save_correction_figure(
        source_doc=_source(json_figure_path=[str(source_path)]),  # type: ignore[arg-type]
        request=request,
    )

    assert len(png_paths) == 1
    assert len(json_paths) == 1
    corrected = pio.from_json(Path(json_paths[0]).read_text(encoding="utf-8"))
    assert corrected.data[-1].name == "Manual correction"
    assert list(corrected.data[-1].x) == [9.95]
    assert list(corrected.data[-1].y) == [-25.0]


@pytest.fixture
def manual_backend(tmp_path, init_db, monkeypatch):
    """Use real service/repository code with in-memory MongoDB and temporary YAML."""
    monkeypatch.setattr("qdash.api.services.manual_update_service.QUBEX_CONFIG_BASE", tmp_path)
    monkeypatch.setattr("qdash.api.services.calibration_github_service.QUBEX_CONFIG_BASE", tmp_path)
    monkeypatch.setattr(
        "qdash.api.services.manual_update_service.get_default_backend", lambda: "qubex"
    )
    ChipDocument(
        project_id="project",
        chip_id="16Q",
        username="tester",
        size=16,
        system_info=SystemInfoModel(),
    ).insert()
    QubitDocument(
        project_id="project",
        chip_id="16Q",
        qid="4",
        username="tester",
        data={"readout_frequency": {"value": 9.0, "unit": "GHz"}, "untouched": {"value": 7}},
        system_info=SystemInfoModel(),
    ).insert()
    params_dir = tmp_path / "16Q" / "params"
    params_dir.mkdir(parents=True)
    path = params_dir / "readout_frequency.yaml"
    path.write_text("# backend\ndata:\n  Q04: 9.0\n  Q05: 8.0\n")
    return ManualUpdateService(), path


@pytest.mark.parametrize("push_failure", [False, True])
def test_manual_edit_pushes_after_local_commit_and_keeps_values_on_failure(
    manual_backend,
    monkeypatch,
    push_failure,
):
    service, path = manual_backend
    monkeypatch.setattr(
        "qdash.api.services.calibration_github_service.config_github_credentials_available",
        lambda: True,
    )
    captured = []

    def publish(files, message, branch):
        assert _qubit_data()["readout_frequency"]["value"] == 10.123
        assert files == {"16Q/params/readout_frequency.yaml": path.read_bytes()}
        assert "manual-edit-" in message
        assert branch == "main"
        captured.append(files)
        TaskResultHistoryDocument.get_motor_collection().update_one(
            {"name": "ManualParameterEdit"}, {"$set": {"note.concurrent_note": "keep me"}}
        )
        if push_failure:
            raise RuntimeError("remote unavailable")
        return "abc123"

    monkeypatch.setattr("qdash.api.services.calibration_github_service.push_config_files", publish)
    result = service.update_parameters(_request(source_task_id=None), "project", "tester")
    assert len(captured) == 1
    assert result.github_sync.status == ("failed" if push_failure else "synced")
    assert _qubit_data()["readout_frequency"]["value"] == 10.123
    assert "10.123" in path.read_text()
    history = TaskResultHistoryDocument.find_one({"task_id": result.task_id}).run()
    assert history is not None
    assert history.status == "completed"
    assert history.note["github_sync"]["status"] == result.github_sync.status
    assert history.note["concurrent_note"] == "keep me"


def test_retry_publishes_current_yaml_without_another_edit(manual_backend, monkeypatch):
    service, path = manual_backend
    result = service.update_parameters(_request(source_task_id=None), "project", "tester")
    path.write_text("data:\n  Q04: 10.2\n")
    monkeypatch.setattr(
        "qdash.api.services.calibration_github_service.config_github_credentials_available",
        lambda: True,
    )
    push = Mock(return_value="abc123")
    monkeypatch.setattr("qdash.api.services.calibration_github_service.push_config_files", push)
    count = TaskResultHistoryDocument.find_all().count()
    sync = service.retry_github_sync(result.task_id, "project")
    assert sync.status == "synced"
    assert push.call_args.args[0] == {"16Q/params/readout_frequency.yaml": path.read_bytes()}
    assert TaskResultHistoryDocument.find_all().count() == count
    assert _qubit_data()["readout_frequency"]["value"] == 10.123
    with pytest.raises(HTTPException, match="not found"):
        service.retry_github_sync(result.task_id, "other-project")
    assert push.call_count == 1


def test_disabled_github_never_pushes_even_with_credentials(manual_backend, monkeypatch):
    service, _ = manual_backend
    result = service.update_parameters(_request(source_task_id=None), "project", "tester")
    monkeypatch.setattr(
        "qdash.api.services.calibration_github_service.config_github_credentials_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "qdash.api.services.calibration_github_service.ConfigLoader.load_workflow",
        lambda: {"github": {"enabled": False}},
    )
    with patch("qdash.api.services.calibration_github_service.push_config_files") as push:
        assert service.retry_github_sync(result.task_id, "project").status == "disabled"
    push.assert_not_called()


def _qubit_data():
    qubit = QubitDocument.find_one({"project_id": "project", "chip_id": "16Q", "qid": "4"}).run()
    assert qubit is not None
    return qubit.data


def test_manual_update_persists_yaml_and_database(manual_backend):
    from ruamel.yaml import YAML

    service, path = manual_backend
    result = service.update_parameters(_request(source_task_id=None), "project", "tester")

    assert _qubit_data()["readout_frequency"]["value"] == 10.123
    assert _qubit_data()["untouched"] == {"value": 7}
    assert YAML().load(path.read_text())["data"] == {"Q04": 10.123, "Q05": 8.0}
    history = TaskResultHistoryDocument.find_one({"task_id": result.task_id}).run()
    assert history is not None
    assert history.status == "completed"


def test_spectroscopy_correction_also_updates_yaml(manual_backend):
    service, path = manual_backend
    source = _source()
    with patch.object(service, "_validate_source_task", return_value=source):
        result = service.update_parameters(_request(), "project", "tester")
    assert "10.123" in path.read_text()
    history = TaskResultHistoryDocument.find_one({"task_id": result.task_id}).run()
    assert history is not None
    assert history.source_task_id == "source-task"


def test_yaml_failure_does_not_update_database(manual_backend):
    service, _path = manual_backend
    with (
        patch(
            "qdash.common.config.params_updater.YamlParamsUpdater._update_yaml",
            side_effect=OSError("write failed"),
        ),
        pytest.raises(OSError, match="write failed"),
    ):
        service.update_parameters(_request(source_task_id=None), "project", "tester")
    assert _qubit_data()["readout_frequency"]["value"] == 9.0
    history = TaskResultHistoryDocument.find_one({"name": "ManualParameterEdit"}).run()
    assert history is not None
    assert history.status == "failed"


@pytest.mark.parametrize("missing", [False, True])
def test_database_failure_restores_yaml(manual_backend, missing):
    service, path = manual_backend
    before = path.read_bytes()
    if missing:
        path.unlink()
    with (
        patch.object(
            service._qubit_repo, "update_calib_data", side_effect=RuntimeError("DB failed")
        ),
        pytest.raises(RuntimeError, match="DB failed"),
    ):
        service.update_parameters(_request(source_task_id=None), "project", "tester")
    if missing:
        assert not path.exists()
    else:
        assert path.read_bytes() == before
    assert _qubit_data()["readout_frequency"]["value"] == 9.0


def test_manual_update_creates_missing_yaml(manual_backend):
    from ruamel.yaml import YAML

    service, path = manual_backend
    path.unlink()
    result = service.update_parameters(_request(source_task_id=None), "project", "tester")
    assert YAML().load(path.read_text()) == {"data": {"Q04": 10.123}}
    assert _qubit_data()["readout_frequency"]["value"] == 10.123
    history = TaskResultHistoryDocument.find_one({"task_id": result.task_id}).run()
    assert history is not None
    assert history.status == "completed"


def test_failure_after_database_write_restores_database_and_yaml(manual_backend):
    service, path = manual_backend
    before = path.read_bytes()
    with (
        patch.object(
            QubitHistoryDocument, "create_history", side_effect=RuntimeError("history failed")
        ),
        pytest.raises(RuntimeError, match="history failed"),
    ):
        service.update_parameters(
            _request(
                source_task_id=None,
                parameters={
                    "readout_frequency": {"value": 10.123},
                    "new_diagnostic": {"value": 2},
                },
            ),
            "project",
            "tester",
        )
    assert path.read_bytes() == before
    assert _qubit_data() == {
        "readout_frequency": {"value": 9.0, "unit": "GHz"},
        "untouched": {"value": 7},
    }


def test_database_only_diagnostic_does_not_require_yaml(manual_backend):
    service, path = manual_backend
    path.unlink()
    service.update_parameters(
        _request(source_task_id=None, parameters={"coarse_qubit_frequency": {"value": 4.2}}),
        "project",
        "tester",
    )
    assert _qubit_data()["coarse_qubit_frequency"]["value"] == 4.2


def test_foreign_project_cannot_change_yaml(manual_backend):
    service, path = manual_backend
    before = path.read_bytes()
    with pytest.raises(HTTPException, match="Chip not found"):
        service.update_parameters(_request(source_task_id=None), "other-project", "tester")
    assert path.read_bytes() == before


def test_chip_path_traversal_cannot_change_yaml(manual_backend):
    service, path = manual_backend
    before = path.read_bytes()
    with pytest.raises(HTTPException, match="Invalid chip ID"):
        service.update_parameters(
            _request(source_task_id=None, chip_id="../16Q"), "project", "tester"
        )
    assert path.read_bytes() == before


@pytest.mark.parametrize("history_failure", [False, True])
def test_coupling_update_and_rollback_use_coupling_label(manual_backend, history_failure):
    from ruamel.yaml import YAML

    service, qubit_path = manual_backend
    CouplingDocument(
        project_id="project",
        chip_id="16Q",
        qid="4-5",
        username="tester",
        data={"zx90_gate_fidelity": {"value": 0.9}},
        system_info=SystemInfoModel(),
    ).insert()
    path = qubit_path.parent / "zx90_gate_fidelity.yaml"
    path.write_text("data:\n  Q04-Q05: 0.9\n")
    request = _request(
        source_task_id=None,
        qid="4-5",
        parameters={"zx90_gate_fidelity": {"value": 0.99}},
    )
    if history_failure:
        with (
            patch.object(
                CouplingHistoryDocument,
                "create_history",
                side_effect=RuntimeError("history failed"),
            ),
            pytest.raises(RuntimeError, match="history failed"),
        ):
            service.update_parameters(request, "project", "tester")
    else:
        service.update_parameters(request, "project", "tester")
    expected = 0.9 if history_failure else 0.99
    coupling = CouplingDocument.find_one(
        {"project_id": "project", "chip_id": "16Q", "qid": "4-5"}
    ).run()
    assert coupling is not None
    assert coupling.data["zx90_gate_fidelity"]["value"] == expected
    assert YAML().load(path.read_text())["data"] == {"Q04-Q05": expected}
