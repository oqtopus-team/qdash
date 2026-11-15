"""Manual rounds in declarative pipeline specs: schema, catalog, digest and dry run."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from qdash.api.services.calibration_pipeline_service import CalibrationPipelineService
from qdash.api.services.manual_round_checks import ChipRoundModel
from qdash.datamodel.calibration_pipeline import (
    CalibrationPipelineSpec,
    pipeline_spec_json_schema,
)

WIRING = [
    {"mux": mux, "ctrl": [f"Q{mux}A-2"], "read_out": f"Q{mux}A-1", "read_in": f"Q{mux}A-0"}
    for mux in range(4)
]
MODEL = ChipRoundModel(wiring=WIRING, coupling_ids=frozenset({"0-1", "4-5", "8-9"}))


def _spec(*steps: dict[str, Any], targets: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "spec_version": 2,
        "targets": targets or {"qids": ["0", "8", "1", "9"]},
        "steps": list(steps),
    }


def _custom_1q(**fields: Any) -> dict[str, Any]:
    return {"type": "CustomOneQubit", "tasks": [{"name": "CheckRabi"}], **fields}


def _custom_2q(**fields: Any) -> dict[str, Any]:
    return {"type": "CustomTwoQubit", "tasks": [{"name": "CheckCrossResonance"}], **fields}


def _service(model: ChipRoundModel = MODEL) -> tuple[CalibrationPipelineService, list[str]]:
    loads: list[str] = []

    def chip_model(project_id: str, chip_id: str) -> ChipRoundModel:
        loads.append(f"{project_id}:{chip_id}")
        return model

    repository = MagicMock()
    repository.list_by_project.return_value = []
    service = CalibrationPipelineService(
        repository,
        default_backend=lambda: "fake",
        available_backends=lambda: ["fake"],
        backend_tasks=lambda _backend: [],
        chip_round_model=chip_model,
    )
    return service, loads


def _problems(spec: dict[str, Any], model: ChipRoundModel = MODEL) -> list[tuple[str, str]]:
    service, _ = _service(model)
    problems: list[Any] = []
    service._validate_manual_rounds(
        "project", "chip", CalibrationPipelineSpec.model_validate(spec), problems
    )
    return [(problem.path, problem.message) for problem in problems]


def test_schema_and_catalog_expose_manual_modes() -> None:
    definitions = pipeline_spec_json_schema()["$defs"]
    for name in ("OneQubitCheckStep", "OneQubitFineTuneStep", "CustomOneQubitStep"):
        assert "manual" in definitions[name]["properties"]["execution_mode"]["enum"]
        assert "rounds" in definitions[name]["properties"]
    for name in ("TwoQubitCalibrationStep", "CustomTwoQubitStep"):
        mode = definitions[name]["properties"]["execution_mode"]
        assert mode["default"] == "automatic" and set(mode["enum"]) == {"automatic", "manual"}
    catalog = _service()[0].catalog("project", "fake")
    assert catalog.one_qubit_execution_modes[-1] == "manual"
    assert catalog.two_qubit_execution_modes == ["automatic", "manual"]


def test_automatic_specs_dump_and_digest_as_before() -> None:
    spec = CalibrationPipelineSpec.model_validate(
        _spec(_custom_1q(), _custom_2q(), {"type": "TwoQubitCalibration", "max_parallel_ops": 4})
    )
    dump = spec.model_dump(mode="json")
    for step in dump["steps"]:
        assert "rounds" not in step
    assert "execution_mode" not in dump["steps"][1] and "execution_mode" not in dump["steps"][2]
    # The digest of an automatic spec does not depend on the new fields' defaults.
    explicit = _spec(
        _custom_1q(),
        _custom_2q(execution_mode="automatic"),
        {"type": "TwoQubitCalibration", "max_parallel_ops": 4},
    )
    assert CalibrationPipelineSpec.model_validate(explicit).plan_digest() == spec.plan_digest()


def test_manual_specs_round_trip_through_their_dump() -> None:
    spec = CalibrationPipelineSpec.model_validate(
        _spec(
            _custom_1q(execution_mode="manual", rounds=[["0", "8"], ["1", "9"]]),
            _custom_2q(execution_mode="manual", rounds=[[["0", "1"]], [["8", "9"]]]),
        )
    )
    dump = spec.model_dump(mode="json")
    assert "max_parallel_ops" not in dump["steps"][1]
    again = CalibrationPipelineSpec.model_validate(dump)
    assert again.plan_digest() == spec.plan_digest()


@pytest.mark.parametrize(
    ("step", "message"),
    [
        (_custom_1q(rounds=[["0"]]), "rounds is only accepted with execution_mode='manual'"),
        (_custom_1q(execution_mode="manual"), "requires rounds"),
        (_custom_1q(execution_mode="manual", rounds=[[0]]), "Input should be a valid string"),
        (
            _custom_2q(execution_mode="manual", rounds=[[["0", "1"]]], max_parallel_ops=10),
            "max_parallel_ops only caps automatic CR groups",
        ),
        (_custom_2q(execution_mode="manual", rounds=[[["0", "1", "2"]]]), "at most 2 items"),
        (_custom_2q(execution_mode="scheduled"), "execution_mode"),
    ],
)
def test_spec_validation_rejects_inconsistent_rounds(step: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        CalibrationPipelineSpec.model_validate(_spec(step))


def test_dry_run_checks_rounds_against_the_chip() -> None:
    spec = _spec(
        _custom_1q(execution_mode="manual", rounds=[["0", "1"], ["8", "9"]]),
        _custom_2q(execution_mode="manual", rounds=[[["1", "0"]]]),
    )
    assert _problems(spec) == [
        (
            "steps[0].rounds",
            "round 1 (0, 1): qubits 0 and 1 share MUX 0; qubits of one MUX must run in different "
            "rounds",
        ),
        (
            "steps[0].rounds",
            "round 2 (8, 9): qubits 8 and 9 share MUX 2; qubits of one MUX must run in different "
            "rounds",
        ),
        (
            "steps[1].rounds",
            "round 1 (1-0): 1-0 is not a coupling of the chip; 0-1 is, so swap control and target to run that direction",
        ),
    ]


def test_dry_run_checks_candidates_only_before_the_first_filter() -> None:
    spec = _spec(
        _custom_1q(step_name="first", execution_mode="manual", rounds=[["0", "8"]]),
        {"type": "FilterByStatus", "step": "first"},
        _custom_1q(step_name="second", execution_mode="manual", rounds=[["0"]]),
        targets={"mux_ids": [0, 2], "exclude_qids": ["2", "3", "10", "11"]},
    )
    assert _problems(spec) == [
        (
            "steps[0].rounds",
            "current qubits 1, 9 are in no round; add them to a round or remove them from the "
            "targets",
        )
    ]


def test_specs_without_manual_steps_do_not_read_the_chip() -> None:
    service, loads = _service()
    service._validate_manual_rounds(
        "project", "chip", CalibrationPipelineSpec.model_validate(_spec(_custom_1q())), []
    )
    assert loads == []


def test_missing_wiring_is_a_warning_not_a_pass() -> None:
    service, _ = _service(ChipRoundModel(wiring=None, wiring_error="no wiring file"))
    problems: list[Any] = []
    warnings = service._validate_manual_rounds(
        "project",
        "chip",
        CalibrationPipelineSpec.model_validate(
            _spec(_custom_1q(execution_mode="manual", rounds=[["0", "8"], ["1", "9"]]))
        ),
        problems,
    )
    assert problems == []
    assert [(w.path, w.message) for w in warnings] == [("steps[0].rounds", "no wiring file")]


def test_dry_run_resolves_mux_targets_and_rounds_with_the_topology_mapping() -> None:
    """Sparse MUX IDs and member slots come from the topology, not from ``qid // 4``."""
    from qdash.common.mux_mapping import MuxMapping

    model = ChipRoundModel(
        wiring=[
            {"mux": 9, "ctrl": ["Q9A-0", "Q9A-1", "Q9A-2"], "read_out": "R9A-0"},
            {"mux": 2, "ctrl": ["Q2A-0"], "read_out": "R2A-0"},
        ],
        coupling_ids=frozenset(),
        mux_mapping=MuxMapping.from_groups(
            {9: ["36", "41", "38"], 2: ["5"]}, known_qids=["36", "41", "38", "5", "20"]
        ),
    )
    targets = {"mux_ids": [9, 2], "exclude_qids": ["38"]}
    ok = _spec(_custom_1q(execution_mode="manual", rounds=[["36", "5"], ["41"]]), targets=targets)
    assert _problems(ok, model) == []

    shared = _spec(
        _custom_1q(execution_mode="manual", rounds=[["36", "41"], ["5"]]), targets=targets
    )
    [(path, message)] = _problems(shared, model)
    assert path == "steps[0].rounds" and "share MUX 9" in message


def test_dry_run_rejects_rounds_against_an_unusable_topology() -> None:
    model = ChipRoundModel(wiring=None, mapping_error="the MUX mapping of chip 'chip' is unusable")
    spec = _spec(_custom_1q(execution_mode="manual", rounds=[["0", "8"], ["1", "9"]]))
    assert _problems(spec, model) == [
        ("steps[0].rounds", "the MUX mapping of chip 'chip' is unusable")
    ]
