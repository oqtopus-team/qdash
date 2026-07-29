from typing import Any, cast

import pytest
from fastapi import HTTPException

from qdash.api.services import qubit_parameter_service as qubit_parameter_service_module
from qdash.api.services.qubit_parameter_service import QubitParameterService


class FakeSourceDoc:
    task_id = "source-task"
    name = "CheckT1"
    qid = "4"
    upstream_id = "upstream"
    input_parameters = {"input": {"value": 1}}
    run_parameters = {"run": {"value": 2}}
    task_type = "qubit"
    tags = ["bringup"]
    output_parameters = {
        "t1": {"value": 30.0, "unit": "us"},
        "readout_amplitude": {"value": 0.05, "unit": "a.u.", "derived_from": "optimal_power"},
        "optimal_power": {"value": -26.0, "unit": "dB"},
    }


class FakeActivity:
    def __init__(self, activity_id: str) -> None:
        self.activity_id = activity_id
        self.status = "running"
        self.ended_at = None
        self.saved = False

    def save(self) -> None:
        self.saved = True


class FakeActivityRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.activity = FakeActivity("activity-1")

    def create_activity(self, **kwargs: Any) -> "FakeActivity":
        self.created.append(kwargs)
        return self.activity


class FakeVersion:
    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id


class FakeVersionRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_version(self, **kwargs: Any) -> "FakeVersion":
        self.created.append(kwargs)
        return FakeVersion(f"entity-{kwargs['parameter_name']}")

    def get_by_task(self, project_id: str, task_id: str) -> list["FakeVersion"]:
        _ = project_id
        return [FakeVersion(f"source-entity-{task_id}")]


class FakeRelationRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_relation(self, **kwargs: Any) -> None:
        self.created.append(kwargs)


class FakeQubitRepo:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update_calib_data(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> QubitParameterService:
    inserted: list[dict[str, Any]] = []
    qubit_repo = FakeQubitRepo()
    activity_repo = FakeActivityRepo()
    version_repo = FakeVersionRepo()
    relation_repo = FakeRelationRepo()

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
            inserted.append(self.kwargs)

    class FakeTaskDocument:
        @classmethod
        def find_one(cls, *_args: Any, **_kwargs: Any) -> Any:
            class Result:
                def run(self):
                    return None

            return Result()

    monkeypatch.setattr(
        qubit_parameter_service_module,
        "TaskResultHistoryDocument",
        FakeTaskResultHistoryDocument,
    )
    monkeypatch.setattr(qubit_parameter_service_module, "TaskDocument", FakeTaskDocument)

    instance = QubitParameterService(
        cast("Any", qubit_repo),
        cast("Any", activity_repo),
        cast("Any", version_repo),
        cast("Any", relation_repo),
    )
    instance.inserted_docs = inserted  # type: ignore[attr-defined]
    return instance


def commit(service: QubitParameterService) -> str:
    return service.commit_output_parameters(
        project_id="project",
        chip_id="chip",
        username="alice",
        source_doc=cast("Any", FakeSourceDoc()),
        source_qid="4",
        outputs_by_qid={"4": {"t1": {"value": 42.5, "unit": "us", "description": "d"}}},
        kind="reanalysis",
    )


def test_commit_writes_values_and_history(service: QubitParameterService) -> None:
    execution_id = commit(service)

    assert execution_id.startswith("reanalysis-")

    update_call = cast("Any", service._qubit_repo).updates[0]
    assert update_call["qid"] == "4"
    assert update_call["output_parameters"]["t1"]["value"] == 42.5

    doc = cast("Any", service).inserted_docs[0]
    assert doc["name"] == "CheckT1"
    assert doc["source_task_id"] == "source-task"
    assert "reanalysis" in doc["tags"]


def test_commit_records_provenance(service: QubitParameterService) -> None:
    commit(service)

    activity_repo = cast("Any", service._activity_repo)
    version_repo = cast("Any", service._param_version_repo)
    relation_repo = cast("Any", service._relation_repo)

    assert activity_repo.created[0]["task_name"] == "CheckT1"
    assert activity_repo.created[0]["task_type"] == "reanalysis"
    assert activity_repo.activity.status == "completed"
    assert activity_repo.activity.saved is True

    assert [(v["parameter_name"], v["qid"], v["value"]) for v in version_repo.created] == [
        ("t1", "4", 42.5)
    ]

    relations = [
        (r["relation_type"].value, r["source_id"], r["target_id"]) for r in relation_repo.created
    ]
    # The commit used the source experiment's values and generated the new ones.
    assert ("used", "activity-1", "source-entity-source-task") in relations
    assert ("wasGeneratedBy", "entity-t1", "activity-1") in relations


def test_reject_derived_parameters_blocks_a_derived_value(service: QubitParameterService) -> None:
    with pytest.raises(HTTPException) as exc:
        service.reject_derived_parameters(
            source_doc=cast("Any", FakeSourceDoc()),
            project_id="project",
            names={"readout_amplitude"},
        )

    assert exc.value.status_code == 400
    assert "optimal_power" in exc.value.detail


def test_reject_derived_parameters_blocks_the_source_of_a_derived_value(
    service: QubitParameterService,
) -> None:
    with pytest.raises(HTTPException) as exc:
        service.reject_derived_parameters(
            source_doc=cast("Any", FakeSourceDoc()),
            project_id="project",
            names={"optimal_power"},
        )

    assert exc.value.status_code == 400
    assert "re-analysis" in exc.value.detail


def test_reject_derived_parameters_allows_independent_values(
    service: QubitParameterService,
) -> None:
    service.reject_derived_parameters(
        source_doc=cast("Any", FakeSourceDoc()),
        project_id="project",
        names={"t1"},
    )


def test_ensure_qubit_qid_rejects_coupling_qid() -> None:
    with pytest.raises(HTTPException) as exc:
        QubitParameterService.ensure_qubit_qid("4-5")

    assert exc.value.status_code == 400
    assert "qubits only" in exc.value.detail
