from typing import Any, cast

import pytest
from fastapi import HTTPException

from qdash.api.schemas.calibration import ManualParameterUpdateRequest
from qdash.api.services import manual_update_service as manual_update_service_module
from qdash.api.services import qubit_parameter_service as qubit_parameter_service_module
from qdash.api.services.manual_update_service import ManualUpdateService
from qdash.api.services.qubit_parameter_service import QubitParameterService


class FakeSourceDoc:
    task_id = "source-task"
    name = "CheckT1"
    qid = "4"
    output_parameters = {
        "t1": {"value": 30.0, "unit": "us"},
        "readout_amplitude": {"value": 0.05, "unit": "a.u.", "derived_from": "optimal_power"},
        "optimal_power": {"value": -26.0, "unit": "dB"},
    }


class FakeActivity:
    activity_id = "activity-1"
    status = "running"
    ended_at = None

    def save(self) -> None:
        return


class FakeActivityRepo:
    def create_activity(self, **_kwargs: Any) -> "FakeActivity":
        return FakeActivity()


class FakeVersion:
    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id


class FakeVersionRepo:
    def create_version(self, **kwargs: Any) -> "FakeVersion":
        return FakeVersion(f"entity-{kwargs['parameter_name']}")

    def get_by_task(self, project_id: str, task_id: str) -> list["FakeVersion"]:
        _ = project_id
        return [FakeVersion(f"source-entity-{task_id}")]


class FakeRelationRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_relation(self, **kwargs: Any) -> None:
        self.created.append(kwargs)


class FakeCalibrationRepo:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update_calib_data(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> ManualUpdateService:
    class FakeTaskResultHistoryDocument:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        @classmethod
        def find_one(cls, *_args: Any, **_kwargs: Any) -> Any:
            class Result:
                def run(self):
                    return FakeSourceDoc()

            return Result()

        def insert(self) -> None:
            return

    class FakeTaskDocument:
        @classmethod
        def find_one(cls, *_args: Any, **_kwargs: Any) -> Any:
            class Result:
                def run(self):
                    return None

            return Result()

    for module in (manual_update_service_module, qubit_parameter_service_module):
        monkeypatch.setattr(module, "TaskResultHistoryDocument", FakeTaskResultHistoryDocument)
    monkeypatch.setattr(qubit_parameter_service_module, "TaskDocument", FakeTaskDocument)

    relation_repo = FakeRelationRepo()
    qubit_repo = FakeCalibrationRepo()
    return ManualUpdateService(
        qubit_repo=cast("Any", qubit_repo),
        coupling_repo=cast("Any", FakeCalibrationRepo()),
        activity_repo=cast("Any", FakeActivityRepo()),
        param_version_repo=cast("Any", FakeVersionRepo()),
        relation_repo=cast("Any", relation_repo),
        parameter_service=QubitParameterService(
            cast("Any", qubit_repo),
            cast("Any", FakeActivityRepo()),
            cast("Any", FakeVersionRepo()),
            cast("Any", relation_repo),
        ),
    )


def request_for(
    parameters: dict[str, dict[str, Any]], source_task_id: str | None = "source-task"
) -> ManualParameterUpdateRequest:
    return ManualParameterUpdateRequest(
        chip_id="chip",
        qid="4",
        parameters=parameters,
        source_task_id=source_task_id,
    )


def test_update_links_the_edit_to_its_source_experiment(service: ManualUpdateService) -> None:
    response = service.update_parameters(
        request=request_for({"t1": {"value": 42.5, "unit": "us"}}),
        project_id="project",
        username="alice",
    )

    assert response.updated_count == 1

    relations = [
        (r["relation_type"].value, r["source_id"], r["target_id"])
        for r in cast("Any", service._relation_repo).created
    ]
    assert ("used", "activity-1", "source-entity-source-task") in relations
    assert ("wasGeneratedBy", "entity-t1", "activity-1") in relations


def test_update_without_source_task_stays_free_form(service: ManualUpdateService) -> None:
    # No source task: any parameter name is accepted, as before.
    response = service.update_parameters(
        request=request_for({"anything": {"value": 1.0}}, source_task_id=None),
        project_id="project",
        username="alice",
    )

    assert response.updated_count == 1
    relations = [r["relation_type"].value for r in cast("Any", service._relation_repo).created]
    assert "used" not in relations


def test_update_rejects_a_name_the_source_task_never_produced(
    service: ManualUpdateService,
) -> None:
    with pytest.raises(HTTPException) as exc:
        service.update_parameters(
            request=request_for({"not_a_parameter": {"value": 1.0}}),
            project_id="project",
            username="alice",
        )

    assert exc.value.status_code == 400
    assert "not_a_parameter" in exc.value.detail


def test_update_rejects_derived_parameters(service: ManualUpdateService) -> None:
    with pytest.raises(HTTPException) as exc:
        service.update_parameters(
            request=request_for({"readout_amplitude": {"value": 0.1}}),
            project_id="project",
            username="alice",
        )

    assert exc.value.status_code == 400
    assert "optimal_power" in exc.value.detail
