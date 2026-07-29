import math
from typing import Any, cast

import plotly.graph_objects as go
import pytest
from pydantic import ValidationError

from qdash.api.schemas.reanalysis import (
    ReanalyzeAffectedQubit,
    ReanalyzeOutputParameter,
    ReanalyzeResonatorSpectroscopyParams,
    ReanalyzeResponse,
)
from qdash.api.services import qubit_parameter_service as qubit_parameter_service_module
from qdash.api.services import reanalysis_service as reanalysis_service_module
from qdash.api.services.qubit_parameter_service import QubitParameterService
from qdash.api.services.reanalysis_service import ReanalysisService


def test_pick_resonator_for_qid_uses_manual_slot_override() -> None:
    value = ReanalysisService._pick_resonator_for_qid(
        "0",
        [4.0, 5.0, 6.0, 7.0],
        [4.5, 5.5, 6.5, 7.5],
        assignment_order=[3, 0, 2, 1],
        manual_resonator_slot=2,
    )

    assert value == 6.5


def test_pick_resonator_for_qid_manual_slot_respects_partial_mux_slots() -> None:
    value = ReanalysisService._pick_resonator_for_qid(
        "0",
        [4.0, 5.0, 6.0, 7.0],
        [4.5, 5.5, 7.5],
        assignment_order=[3, 0, 2, 1],
        manual_resonator_slot=2,
    )

    assert value == 0.0


def test_reanalyze_resonator_params_validate_manual_slot_bounds() -> None:
    assert ReanalyzeResonatorSpectroscopyParams(manual_resonator_slot=3).manual_resonator_slot == 3

    with pytest.raises(ValidationError):
        ReanalyzeResonatorSpectroscopyParams(manual_resonator_slot=4)


def test_reanalyze_resonator_params_accept_manual_readout_frequency() -> None:
    params = ReanalyzeResonatorSpectroscopyParams(manual_readout_frequency=5.123456)

    assert params.manual_readout_frequency == 5.123456


def test_reanalyze_resonator_params_reject_non_finite_manual_readout_frequency() -> None:
    with pytest.raises(ValidationError):
        ReanalyzeResonatorSpectroscopyParams(manual_readout_frequency=math.nan)


def test_reanalyze_resonator_params_validate_manual_readout_frequencies() -> None:
    params = ReanalyzeResonatorSpectroscopyParams(manual_readout_frequencies=[4.5, None, 6.5, 7.5])

    assert params.manual_readout_frequencies == [4.5, None, 6.5, 7.5]

    with pytest.raises(ValidationError):
        ReanalyzeResonatorSpectroscopyParams(manual_readout_frequencies=[4.5, 5.5, 6.5])

    with pytest.raises(ValidationError):
        ReanalyzeResonatorSpectroscopyParams(manual_readout_frequencies=[4.5, math.inf, 6.5, 7.5])


def test_reanalyze_resonator_params_validate_output_parameter_overrides() -> None:
    params = ReanalyzeResonatorSpectroscopyParams(
        output_parameter_overrides={"4": {"readout_frequency": 5.5, "anharmonicity": -0.25}}
    )

    assert params.output_parameter_overrides == {
        "4": {"readout_frequency": 5.5, "anharmonicity": -0.25}
    }

    with pytest.raises(ValidationError):
        ReanalyzeResonatorSpectroscopyParams(
            output_parameter_overrides={"4": {"readout_frequency": math.nan}}
        )


def test_apply_output_parameter_overrides_updates_and_adds_parameters() -> None:
    affected = [
        ReanalyzeAffectedQubit(
            qid="4",
            output_parameters=[
                ReanalyzeOutputParameter(name="readout_frequency", value=5.5, unit="GHz")
            ],
        )
    ]

    ReanalysisService._apply_output_parameter_overrides(
        affected,
        {
            "4": {"readout_frequency": 5.625, "anharmonicity": -0.25},
            "5": {"readout_frequency": 7.625},
        },
    )

    assert [
        (item.qid, [(parameter.name, parameter.value) for parameter in item.output_parameters])
        for item in affected
    ] == [
        ("4", [("readout_frequency", 5.625), ("anharmonicity", -0.25)]),
        ("5", [("readout_frequency", 7.625)]),
    ]


def test_add_manual_readout_markers_marks_output_parameter_overrides() -> None:
    fig = go.Figure()

    ReanalysisService._add_manual_readout_markers(
        fig,
        qid="4",
        assignment_order=[3, 0, 2, 1],
        output_parameter_overrides={
            "4": {"readout_frequency": 5.625, "anharmonicity": -0.25},
            "6": {"readout_frequency": 7.125},
        },
    )

    layout = fig.to_dict()["layout"]
    marked = sorted(shape["x0"] for shape in layout["shapes"] if shape["type"] == "line")
    annotations = sorted(annotation["text"] for annotation in layout["annotations"])

    assert marked == [5.625, 7.125]
    assert annotations == ["manual Q4", "manual Q6"]


def test_add_manual_power_markers_stars_the_picked_point() -> None:
    fig = go.Figure()
    affected = [
        ReanalyzeAffectedQubit(
            qid="4",
            output_parameters=[
                ReanalyzeOutputParameter(name="readout_frequency", value=5.625, unit="GHz"),
                ReanalyzeOutputParameter(name="optimal_power", value=-30.0, unit="dB"),
            ],
        ),
        ReanalyzeAffectedQubit(
            qid="5",
            output_parameters=[
                ReanalyzeOutputParameter(name="readout_frequency", value=7.125, unit="GHz"),
                ReanalyzeOutputParameter(name="optimal_power", value=-25.0, unit="dB"),
            ],
        ),
    ]

    ReanalysisService._add_manual_power_markers(
        fig,
        affected_qubits=affected,
        # Only Q4's power was picked, so Q5 gets no star.
        output_parameter_overrides={"4": {"optimal_power": -30.0}},
    )

    traces = fig.to_dict()["data"]

    assert len(traces) == 1
    assert list(traces[0]["x"]) == [5.625]
    assert list(traces[0]["y"]) == [-30.0]
    assert traces[0]["marker"]["symbol"] == "star"
    assert list(traces[0]["text"]) == ["manual Q4"]


def test_apply_current_calibration_values_sets_previous_db_values() -> None:
    class FakeQubitRepo:
        def get_calibration_data(self, *, project_id: str, chip_id: str, qid: str):
            _ = project_id, chip_id
            return {
                "4": {"readout_frequency": {"value": 5.25}, "quality": {"value": True}},
                "5": {"readout_frequency": {"value": 7.25}},
            }.get(qid, {})

    affected = [
        ReanalyzeAffectedQubit(
            qid="4",
            output_parameters=[
                ReanalyzeOutputParameter(name="readout_frequency", value=5.5, unit="GHz"),
                ReanalyzeOutputParameter(name="quality", value=1.0),
            ],
        ),
        ReanalyzeAffectedQubit(
            qid="5",
            output_parameters=[
                ReanalyzeOutputParameter(name="readout_frequency", value=7.5, unit="GHz")
            ],
        ),
    ]

    service = ReanalysisService(qubit_repo=cast("Any", FakeQubitRepo()))

    service._apply_current_calibration_values(affected, project_id="project", chip_id="chip")

    assert affected[0].output_parameters[0].current_value == 5.25
    assert affected[0].output_parameters[1].current_value is None
    assert affected[1].output_parameters[0].current_value == 7.25


def test_apply_snapshot_values_reads_each_mux_qubits_own_task_result(monkeypatch) -> None:
    class SiblingDoc:
        def __init__(self, qid: str, frequency: float) -> None:
            self.qid = qid
            self.output_parameters = {"readout_frequency": {"value": frequency}}

    class SourceDoc:
        qid = "4"
        name = "CheckResonatorSpectroscopy"
        execution_id = "exec-1"
        output_parameters = {"readout_frequency": {"value": 5.4}}

    class FakeFind:
        def run(self):
            return [SiblingDoc("4", 5.4), SiblingDoc("5", 7.4)]

    class FakeTaskResultHistoryDocument:
        @classmethod
        def find(cls, *_args, **_kwargs):
            return FakeFind()

    monkeypatch.setattr(
        reanalysis_service_module,
        "TaskResultHistoryDocument",
        FakeTaskResultHistoryDocument,
    )

    affected = [
        ReanalyzeAffectedQubit(
            qid="4",
            output_parameters=[
                ReanalyzeOutputParameter(name="readout_frequency", value=5.5, unit="GHz")
            ],
        ),
        ReanalyzeAffectedQubit(
            qid="5",
            output_parameters=[
                ReanalyzeOutputParameter(name="readout_frequency", value=7.5, unit="GHz"),
                # No recorded counterpart, e.g. a parameter the original run did not produce.
                ReanalyzeOutputParameter(name="optimal_power", value=-30.0, unit="dB"),
            ],
        ),
    ]

    ReanalysisService._apply_snapshot_values(
        affected, project_id="project", source_doc=cast("Any", SourceDoc())
    )

    assert affected[0].output_parameters[0].snapshot_value == 5.4
    assert affected[1].output_parameters[0].snapshot_value == 7.4
    assert affected[1].output_parameters[1].snapshot_value is None


def test_outputs_are_committable_accepts_negative_finite_values() -> None:
    assert ReanalysisService._outputs_are_committable(
        [ReanalyzeOutputParameter(name="anharmonicity", value=-0.25, unit="GHz")]
    )
    assert not ReanalysisService._outputs_are_committable([])


def test_build_resonator_affected_qubits_maps_all_mux_slots() -> None:
    affected = ReanalysisService._build_resonator_affected_qubits(
        "4",
        [4.0, 5.0, 6.0, 7.0],
        [4.5, 5.5, 6.5, 7.5],
        assignment_order=[3, 0, 2, 1],
    )

    assert [(item.qid, item.output_parameters[0].value) for item in affected] == [
        ("4", 5.5),
        ("5", 7.5),
        ("6", 6.5),
        ("7", 4.5),
    ]


def test_build_resonator_affected_qubits_adds_optimal_power_and_amplitude() -> None:
    affected = ReanalysisService._build_resonator_affected_qubits(
        "4",
        [4.0, 5.0, 6.0, 7.0],
        [4.5, 5.5, 6.5, 7.5],
        optimal_powers=[-20.0, -30.0, -40.0, -50.0],
        assignment_order=[3, 0, 2, 1],
    )

    by_qid = {item.qid: item.output_parameters for item in affected}

    assert [(parameter.name, parameter.unit) for parameter in by_qid["4"]] == [
        ("readout_frequency", "GHz"),
        ("optimal_power", "dB"),
        ("readout_amplitude", "a.u."),
    ]
    # Q4 sits on the second sorted slot, so it takes the second optimal power.
    assert by_qid["4"][1].value == -30.0
    assert by_qid["4"][2].value == pytest.approx(10 ** (-30.0 / 20))


def test_derive_readout_amplitudes_follows_overridden_optimal_power() -> None:
    affected = [
        ReanalyzeAffectedQubit(
            qid="4",
            output_parameters=[
                ReanalyzeOutputParameter(name="optimal_power", value=-26.0, unit="dB"),
                ReanalyzeOutputParameter(name="readout_amplitude", value=0.05, unit="a.u."),
            ],
        ),
        ReanalyzeAffectedQubit(
            qid="5",
            output_parameters=[
                ReanalyzeOutputParameter(name="optimal_power", value=-26.0, unit="dB"),
                ReanalyzeOutputParameter(name="readout_amplitude", value=0.05, unit="a.u."),
            ],
        ),
    ]

    ReanalysisService._derive_readout_amplitudes(
        affected,
        {
            "4": {"optimal_power": -20.0},
            # An explicit amplitude override wins over the derived value.
            "5": {"optimal_power": -20.0, "readout_amplitude": 0.5},
        },
    )

    assert affected[0].output_parameters[1].value == pytest.approx(10 ** (-20.0 / 20))
    assert affected[1].output_parameters[1].value == 0.05


def test_build_resonator_affected_qubits_applies_manual_slot_frequencies() -> None:
    affected = ReanalysisService._build_resonator_affected_qubits(
        "4",
        [4.0, 5.0, 6.0, 7.0],
        [4.5, 5.5, 6.5, 7.5],
        assignment_order=[3, 0, 2, 1],
        manual_readout_frequencies=[4.625, 5.625, None, 7.625],
    )

    assert [(item.qid, item.output_parameters[0].value) for item in affected] == [
        ("4", 5.625),
        ("5", 7.625),
        ("6", 6.5),
        ("7", 4.625),
    ]


def test_build_resonator_affected_qubits_applies_manual_frequency_to_selected_qid() -> None:
    affected = ReanalysisService._build_resonator_affected_qubits(
        "4",
        [4.0, 5.0, 6.0, 7.0],
        [4.5, 5.5, 6.5, 7.5],
        assignment_order=[3, 0, 2, 1],
        manual_readout_frequency=5.125,
    )

    assert [(item.qid, item.output_parameters[0].value) for item in affected] == [
        ("4", 5.125),
        ("5", 7.5),
        ("6", 6.5),
        ("7", 4.5),
    ]


def test_commit_reanalyze_resonator_spectroscopy_updates_all_affected_qubits(monkeypatch) -> None:
    inserted_docs: list[dict[str, object]] = []

    class FakeFindOne:
        def run(self):
            return FakeSourceDoc()

    class FakeSourceDoc:
        task_id = "source-task"
        name = "CheckResonatorSpectroscopy"
        upstream_id = "upstream"
        input_parameters = {"input": {"value": 1}}
        run_parameters = {"run": {"value": 2}}
        task_type = "qubit"
        tags = ["bringup"]

    class FakeTaskResultHistoryDocument:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        @classmethod
        def find_one(cls, *_args, **_kwargs):
            return FakeFindOne()

        def insert(self) -> None:
            inserted_docs.append(self.kwargs)

    class FakeQubitRepo:
        def __init__(self) -> None:
            self.updates: list[dict[str, object]] = []

        def update_calib_data(self, **kwargs) -> None:
            self.updates.append(kwargs)

    class FakeActivity:
        activity_id = "activity-1"
        status = "running"
        ended_at = None

        def save(self) -> None:
            return None

    class FakeActivityRepo:
        def create_activity(self, **_kwargs):
            return FakeActivity()

    class FakeVersion:
        entity_id = "entity-1"

    class FakeVersionRepo:
        def create_version(self, **_kwargs):
            return FakeVersion()

        def get_by_task(self, *_args, **_kwargs):
            return []

    class FakeRelationRepo:
        def create_relation(self, **_kwargs):
            return None

    repo = FakeQubitRepo()
    service = ReanalysisService(
        qubit_repo=cast("Any", repo),
        parameter_service=QubitParameterService(
            cast("Any", repo),
            cast("Any", FakeActivityRepo()),
            cast("Any", FakeVersionRepo()),
            cast("Any", FakeRelationRepo()),
        ),
    )

    def fake_reanalyze(**_kwargs) -> ReanalyzeResponse:
        return ReanalyzeResponse(
            source_task_id="source-task",
            source_task_name="CheckResonatorSpectroscopy",
            qid="4",
            figure={},
            output_parameters=[
                ReanalyzeOutputParameter(name="readout_frequency", value=5.5, unit="GHz")
            ],
            affected_qubits=[
                ReanalyzeAffectedQubit(
                    qid="4",
                    output_parameters=[
                        ReanalyzeOutputParameter(name="readout_frequency", value=5.5, unit="GHz")
                    ],
                ),
                ReanalyzeAffectedQubit(
                    qid="5",
                    output_parameters=[
                        ReanalyzeOutputParameter(name="readout_frequency", value=7.5, unit="GHz")
                    ],
                ),
            ],
        )

    monkeypatch.setattr(service, "reanalyze_resonator_spectroscopy", fake_reanalyze)
    monkeypatch.setattr(
        qubit_parameter_service_module,
        "TaskResultHistoryDocument",
        FakeTaskResultHistoryDocument,
    )

    response = service.commit_reanalyze_resonator_spectroscopy(
        project_id="project",
        chip_id="chip",
        qid="4",
        params=ReanalyzeResonatorSpectroscopyParams(),
        source_task_id="source-task",
        username="alice",
    )

    assert response.committed is True
    assert [update["qid"] for update in repo.updates] == ["4", "5"]
    assert [doc["qid"] for doc in inserted_docs] == ["4", "5"]
    assert all(doc["name"] == "CheckResonatorSpectroscopy" for doc in inserted_docs)
    assert all(doc["source_task_id"] == "source-task" for doc in inserted_docs)
