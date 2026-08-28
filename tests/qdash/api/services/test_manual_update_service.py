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
