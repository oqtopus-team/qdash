import copy
import sys
import types
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import plotly.graph_objects as go
import pytest

from qdash.analysis.spectroscopy.estimate_resonator_frequency import Peak, Resonance
from qdash.common.config.backend import get_tasks
from qdash.datamodel.calibration_pipeline import BRINGUP_TASKS
from qdash.workflow.calibtasks.base import BaseTask, RunResult
from qdash.workflow.calibtasks.qubex.cw.check_qubit_frequency_mapping import (
    MAX_RESONATOR_CANDIDATES,
    CheckQubitFrequencyMapping,
    candidate_source_error,
    load_multiplexed_readout_qubit_spectroscopy,
)
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import (
    compute_coarse_control_amplitude,
)
from qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy import (
    CheckResonatorSpectroscopy,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any

MODULE = "qdash.workflow.calibtasks.qubex.cw.check_qubit_frequency_mapping"
SLOTS = ["RQ00", "RQ01", "RQ02", "RQ03"]
READOUT_FREQUENCIES = [10.21, 10.29, 10.36, 10.43]
READOUT_AMPLITUDES = [0.02, 0.03, 0.04, 0.05]
DRIVE_FREQUENCIES = np.round(np.arange(4.0, 4.5, 0.005), 6)
DRIVE_POWERS = np.arange(-60.0, 0.0, 5.0)
RESPONSE_INDEX = 40


def _set_candidate_inputs(
    task: CheckQubitFrequencyMapping,
    frequencies: list[float | None],
    amplitudes: list[float | None],
    *,
    count: int | float | None = None,
    execution_id: str = "exec-resonator",
    task_id: str = "task-resonator",
) -> None:
    task.input_parameters = copy.deepcopy(task.input_parameters)
    count_param = task.input_parameters["resonator_candidate_count"]
    count_param.value = len(frequencies) if count is None else count
    count_param.execution_id = execution_id
    count_param.task_id = task_id
    for index, (frequency, amplitude) in enumerate(zip(frequencies, amplitudes, strict=True)):
        for field, value in (("frequency", frequency), ("readout_amplitude", amplitude)):
            parameter = task.input_parameters[f"resonator_candidate_{index}_{field}"]
            parameter.value = value
            parameter.execution_id = execution_id
            parameter.task_id = task_id


def _response_z(center: int, amplitude: float = 3.0) -> np.ndarray:
    """Return a qubit mountain whose width grows with drive power."""
    rng = np.random.default_rng(center)
    zs = rng.normal(0.0, 0.05, size=(len(DRIVE_POWERS), len(DRIVE_FREQUENCIES)))
    for row, power in enumerate(DRIVE_POWERS):
        if power < -35.0:
            continue
        half_width = int((power + 35.0) / 5.0)
        zs[row, center - half_width : center + half_width + 1] = amplitude
    return zs


def _noise_z(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 0.05, size=(len(DRIVE_POWERS), len(DRIVE_FREQUENCIES)))


def _contrib_result(
    zs_by_slot: dict[str, np.ndarray],
    *,
    target: str = "Q01",
    frequencies: list[float] | None = None,
    amplitudes: list[float] | None = None,
) -> SimpleNamespace:
    frequencies = READOUT_FREQUENCIES if frequencies is None else frequencies
    amplitudes = READOUT_AMPLITUDES if amplitudes is None else amplitudes
    slots = list(zs_by_slot)
    candidates = {
        slot: {
            "readout_label": slot,
            "candidate_index": index,
            "readout_frequency": frequencies[index],
            "readout_amplitude": amplitudes[index],
            "frequency_range": DRIVE_FREQUENCIES.copy(),
            "power_range": DRIVE_POWERS.copy(),
            "signals": np.exp(1j * zs),
            "phases": zs,
            "data": zs,
        }
        for index, (slot, zs) in enumerate(zs_by_slot.items())
    }
    figures = {
        slot: go.Figure(go.Heatmap(x=DRIVE_FREQUENCIES, y=DRIVE_POWERS, z=zs))
        for slot, zs in zs_by_slot.items()
    }
    return SimpleNamespace(
        data={
            "target": target,
            "readout_labels": slots,
            "frequency_range": DRIVE_FREQUENCIES.copy(),
            "power_range": DRIVE_POWERS.copy(),
            "candidates": candidates,
        },
        figures=figures,
        figure=figures[slots[0]],
    )


def _experiment(slots: list[str] | None = None) -> MagicMock:
    exp = MagicMock()
    resonators = [SimpleNamespace(label=label, is_valid=True) for label in (slots or SLOTS)]
    exp.ctx.experiment_system.get_mux_by_qubit.return_value = SimpleNamespace(
        resonators=tuple(reversed(resonators))
    )
    return exp


def _run(
    task: CheckQubitFrequencyMapping, result: Any, exp: MagicMock | None = None
) -> tuple[RunResult, MagicMock]:
    """Run the task with the source-freshness check stubbed; persistence tests cover it."""
    exp = exp or _experiment()
    contrib = MagicMock(return_value=result)
    with (
        patch.object(task, "get_experiment", return_value=exp),
        patch.object(task, "get_qubit_label", return_value="Q01"),
        patch.object(task, "_verify_candidate_source") as verify,
        patch(f"{MODULE}.load_multiplexed_readout_qubit_spectroscopy", return_value=contrib),
    ):
        run_result = task.run(cast("QubexBackend", object()), "1")
    verify.assert_called_once()
    return run_result, contrib


def _postprocess(task: CheckQubitFrequencyMapping, run_result: RunResult):
    return task.postprocess(cast("QubexBackend", object()), "exec-map", run_result, "1")


def _task_with_candidates() -> CheckQubitFrequencyMapping:
    task = CheckQubitFrequencyMapping()
    _set_candidate_inputs(task, list(READOUT_FREQUENCIES), list(READOUT_AMPLITUDES))
    return task


def _single_response_result(response_slot: str = "RQ02") -> SimpleNamespace:
    return _contrib_result(
        {
            slot: _response_z(RESPONSE_INDEX) if slot == response_slot else _noise_z(index)
            for index, slot in enumerate(SLOTS)
        }
    )


def test_task_is_registered_as_an_opt_in_per_qubit_qubex_task() -> None:
    """Register the task for qubex without adding it to default bring-up."""
    assert BaseTask.registry["qubex"]["CheckQubitFrequencyMapping"] is CheckQubitFrequencyMapping
    assert CheckQubitFrequencyMapping.task_type == "qubit"
    assert getattr(CheckQubitFrequencyMapping, "is_mux_level", False) is False
    assert "CheckQubitFrequencyMapping" in get_tasks("qubex")
    assert all(call.name != "CheckQubitFrequencyMapping" for call in BRINGUP_TASKS)


def test_outputs_publish_the_same_destinations_as_the_spectroscopy_tasks() -> None:
    """Publish frequencies to the measured and operational parameters of existing tasks."""
    spec = CheckQubitFrequencyMapping.output_spec

    assert spec["resonator_frequency"].publish_targets == (
        "resonator_frequency",
        "readout_frequency",
    )
    assert spec["coarse_qubit_frequency"].publish_targets == (
        "coarse_qubit_frequency",
        "control_frequency",
    )
    assert {"readout_amplitude", "coarse_control_amplitude", "f01_quality_level"} <= set(spec)


def test_candidate_inputs_cover_the_producer_outputs_and_forbid_overrides() -> None:
    """Declare one forbidden-override input for every candidate output of the producer."""
    producer_names = {
        name for name in CheckResonatorSpectroscopy.output_spec if name.startswith("resonator_c")
    }

    assert set(CheckQubitFrequencyMapping.input_spec) == producer_names
    assert len(producer_names) == 1 + 2 * MAX_RESONATOR_CANDIDATES
    assert all(
        spec.user_override == "forbidden" for spec in CheckQubitFrequencyMapping.input_spec.values()
    )


def test_missing_contrib_helper_raises_actionable_error(monkeypatch) -> None:
    """Explain the Qubex prerequisite when the installed qubex lacks the helper."""
    monkeypatch.setitem(sys.modules, "qubex.contrib", types.ModuleType("qubex.contrib"))

    with pytest.raises(RuntimeError, match=r"amachino/qubex/pull/472"):
        load_multiplexed_readout_qubit_spectroscopy()


def test_run_drives_one_target_and_reads_every_paired_candidate() -> None:
    """Pass one drive target and each candidate frequency with its own amplitude."""
    task = _task_with_candidates()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["frequency_range"].value = (4.0, 4.5, 0.005)
    task.run_parameters["shots"].value = 321
    task.run_parameters["interval"].value = 654.0
    task.run_parameters["simultaneous_drive"].value = False

    _, contrib = _run(task, _single_response_result())

    contrib.assert_called_once()
    args, kwargs = contrib.call_args
    assert args[1] == "Q01"
    assert kwargs["readout_frequencies"] == dict(zip(SLOTS, READOUT_FREQUENCIES, strict=True))
    assert kwargs["readout_amplitudes"] == dict(zip(SLOTS, READOUT_AMPLITUDES, strict=True))
    assert list(kwargs["readout_frequencies"]) == SLOTS
    assert kwargs["shots"] == 321
    assert kwargs["interval"] == 654.0
    assert kwargs["simultaneous_drive"] is False
    assert list(kwargs["power_range"]) == pytest.approx(list(DRIVE_POWERS))
    assert kwargs["plot"] is False
    assert kwargs["save_image"] is False


def test_run_uses_only_as_many_slots_as_candidates() -> None:
    """Use the first sorted MUX readout slots for a partial candidate set."""
    task = CheckQubitFrequencyMapping()
    _set_candidate_inputs(task, [10.21, 10.29], [0.02, 0.03])

    _, contrib = _run(task, _single_response_result())

    assert contrib.call_args.kwargs["readout_frequencies"] == {"RQ00": 10.21, "RQ01": 10.29}


@pytest.mark.parametrize(
    ("frequencies", "amplitudes", "count", "match"),
    [
        ([], [], 0, "resonator_candidate_count"),
        ([10.2, 10.3], [0.02, 0.03], 5, "resonator_candidate_count"),
        ([10.2, 10.3], [0.02, 0.03], 2.5, "resonator_candidate_count"),
        ([10.2, None], [0.02, 0.03], None, "resonator_candidate_1_frequency"),
        ([10.2, 10.3], [0.02, float("nan")], None, "resonator_candidate_1_readout_amplitude"),
        ([10.2, 10.3], [0.02, 0.0], None, "resonator_candidate_1_readout_amplitude"),
        ([10.3, 10.2], [0.02, 0.03], None, "strictly increasing"),
        ([10.2, 10.2], [0.02, 0.03], None, "strictly increasing"),
    ],
)
def test_malformed_candidate_set_is_rejected_before_hardware(
    frequencies, amplitudes, count, match
) -> None:
    """Reject missing, non-finite, out-of-range, or unordered candidates before measuring."""
    task = CheckQubitFrequencyMapping()
    _set_candidate_inputs(task, frequencies, amplitudes, count=count)

    with pytest.raises(ValueError, match=match):
        _run(task, _single_response_result())


def test_candidates_from_different_source_runs_are_rejected() -> None:
    """Reject a candidate whose provenance differs from the candidate count."""
    task = _task_with_candidates()
    task.input_parameters["resonator_candidate_2_frequency"].task_id = "older-task"

    with pytest.raises(ValueError, match="same CheckResonatorSpectroscopy result"):
        _run(task, _single_response_result())


def test_candidate_set_without_provenance_is_rejected() -> None:
    """Require the candidate set to identify the run that produced it."""
    task = CheckQubitFrequencyMapping()
    _set_candidate_inputs(task, [10.2], [0.02], execution_id="", task_id="")

    with pytest.raises(ValueError, match="provenance"):
        _run(task, _single_response_result())


def test_too_few_readout_slots_are_rejected() -> None:
    """Reject a candidate set larger than the target's configured MUX slots."""
    task = _task_with_candidates()

    with pytest.raises(ValueError, match="readout slots"):
        _run(task, _single_response_result(), exp=_experiment(["RQ00", "RQ01"]))


def test_unique_response_identifies_qubit_frequency_and_resonator() -> None:
    """Publish the responding candidate's readout and coarse qubit values."""
    task = _task_with_candidates()
    run_result, _ = _run(task, _single_response_result("RQ02"))

    result = _postprocess(task, run_result)

    outputs = result.output_parameters
    assert result.validation_error is None
    assert outputs["resonator_candidate_index"].value == 2
    assert outputs["resonator_frequency"].value == READOUT_FREQUENCIES[2]
    assert outputs["readout_amplitude"].value == READOUT_AMPLITUDES[2]
    assert outputs["coarse_qubit_frequency"].value == pytest.approx(
        DRIVE_FREQUENCIES[RESPONSE_INDEX]
    )
    assert outputs["f01_quality_level"].value >= 3
    expected_amplitude, _ = compute_coarse_control_amplitude(outputs["f01_repr_db"].value)
    assert outputs["coarse_control_amplitude"].value == pytest.approx(expected_amplitude)
    assert all(value.execution_id == "exec-map" for value in outputs.values())
    assert len(result.figures) == 1 + 2 * len(SLOTS)


def test_wrong_existing_assignment_does_not_change_the_selection() -> None:
    """Select by response even when the qid's existing readout points elsewhere."""
    task = _task_with_candidates()
    task.input_parameters = copy.deepcopy(task.input_parameters)
    run_result, _ = _run(task, _single_response_result("RQ00"))

    result = _postprocess(task, run_result)

    assert result.validation_error is None
    assert result.output_parameters["resonator_candidate_index"].value == 0
    assert result.output_parameters["resonator_frequency"].value == READOUT_FREQUENCIES[0]


def test_no_response_publishes_nothing_and_keeps_figures() -> None:
    """Fail without outputs when no candidate shows a qubit response."""
    task = _task_with_candidates()
    run_result, _ = _run(task, _contrib_result({slot: _noise_z(i) for i, slot in enumerate(SLOTS)}))

    result = _postprocess(task, run_result)

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "No readout candidate" in result.validation_error
    assert len(result.figures) == 1 + 2 * len(SLOTS)


def test_two_similar_measured_responses_publish_nothing() -> None:
    """Fail as ambiguous when two candidates show equally strong measured responses."""
    task = _task_with_candidates()
    zs = {slot: _noise_z(i) for i, slot in enumerate(SLOTS)}
    zs["RQ01"] = _response_z(RESPONSE_INDEX)
    zs["RQ03"] = _response_z(RESPONSE_INDEX + 10)
    run_result, _ = _run(task, _contrib_result(zs))

    result = _postprocess(task, run_result)

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "Ambiguous" in result.validation_error
    assert "1" in result.validation_error and "3" in result.validation_error


def test_partially_failed_candidate_analysis_publishes_nothing() -> None:
    """Fail when any candidate cannot be analyzed, even if another responds."""
    task = _task_with_candidates()
    zs = {slot: _noise_z(i) for i, slot in enumerate(SLOTS)}
    zs["RQ02"] = _response_z(RESPONSE_INDEX)
    zs["RQ03"][0, 0] = np.nan
    run_result, _ = _run(task, _contrib_result(zs))

    result = _postprocess(task, run_result)

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "RQ03" in result.validation_error


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda result: result.data["candidates"].pop("RQ01"),
        lambda result: result.data["candidates"]["RQ01"].update(readout_label="RQ02"),
        lambda result: result.data["candidates"]["RQ01"].update(candidate_index=3),
        lambda result: result.data["candidates"]["RQ01"].update(readout_frequency=10.3),
        lambda result: result.data["candidates"]["RQ01"].update(readout_amplitude=0.5),
        lambda result: result.data["candidates"]["RQ01"].update(data=np.zeros((2, 2))),
        lambda result: result.data["candidates"]["RQ01"].update(
            data=result.data["candidates"]["RQ01"]["phases"] + 0.1
        ),
        lambda result: result.data["candidates"]["RQ01"].pop("phases"),
        lambda result: result.data["candidates"]["RQ01"].update(
            phases=result.data["candidates"]["RQ01"]["phases"].T
        ),
        lambda result: result.data["candidates"]["RQ01"].update(
            phases=np.exp(1j * result.data["candidates"]["RQ01"]["phases"])
        ),
        lambda result: result.data["candidates"]["RQ01"]["phases"].__setitem__((0, 0), np.inf),
        lambda result: result.data["candidates"]["RQ01"].update(
            frequency_range=DRIVE_FREQUENCIES + 0.05
        ),
        lambda result: result.data["candidates"]["RQ01"].update(
            power_range=DRIVE_POWERS[::-1].copy()
        ),
        lambda result: result.data["candidates"]["RQ01"].pop("frequency_range"),
    ],
)
def test_malformed_candidate_payload_publishes_nothing(corrupt) -> None:
    """Fail when a candidate's payload does not match the requested pairing, axes, or data."""
    task = _task_with_candidates()
    contrib_result = _single_response_result("RQ02")
    corrupt(contrib_result)
    run_result, _ = _run(task, contrib_result)

    result = _postprocess(task, run_result)

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "RQ01" in result.validation_error


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda result: result.data.update(target="Q02"),
        lambda result: result.data.update(readout_labels=["RQ01", "RQ00", "RQ02", "RQ03"]),
        lambda result: result.data.pop("candidates"),
        lambda result: result.data.update(power_range=DRIVE_POWERS + 1.0),
        lambda result: result.data.update(frequency_range=DRIVE_FREQUENCIES[::-1].copy()),
        lambda result: result.data["frequency_range"].__setitem__(0, np.nan),
        lambda result: setattr(result, "data", None),
    ],
)
def test_malformed_result_publishes_nothing(corrupt) -> None:
    """Fail when the common result fields do not match the requested measurement."""
    task = _task_with_candidates()
    contrib_result = _single_response_result("RQ02")
    corrupt(contrib_result)
    run_result, _ = _run(task, contrib_result)

    result = _postprocess(task, run_result)

    assert result.output_parameters == {}
    assert result.validation_error is not None


# The moment thresholds of EstimateQubitFrequencyConfig: (0.1, 1750, 3600, 5000, 15000).
_QUALITY_OF_MOMENT = {0.0: 0, 0.05: 0, 1000.0: 1, 2000.0: 2, 4000.0: 3, 10000.0: 4, 20000.0: 5}


def _estimate(
    moment_by_slot: dict[str, float | None],
    *,
    frequency: float = 4.2,
    quality_by_slot: dict[str, int] | None = None,
):
    """Return a fake analysis that reports the given raw moment per readout slot."""

    def estimate(fig, *_args, **_kwargs):
        slot = fig.layout.meta["readout_label"]
        moment = moment_by_slot.get(slot)
        if moment is None:
            f01 = None
        else:
            quality = (quality_by_slot or {}).get(slot, _QUALITY_OF_MOMENT.get(moment, 3))
            f01 = SimpleNamespace(
                frequency=frequency, repr_db=-30.0, quality_level=quality, moment=moment
            )
        return go.Figure(fig), SimpleNamespace(f01=f01, f12=None, anharmonicity=None)

    return estimate


def _tagged_result() -> SimpleNamespace:
    return _single_response_result("RQ02")


def _postprocess_with(task: CheckQubitFrequencyMapping, estimate) -> Any:
    run_result, _ = _run(task, _tagged_result())
    with patch(f"{MODULE}.estimate_and_mark_qubit_figure", side_effect=estimate):
        return _postprocess(task, run_result)


def _evidence(result) -> dict[str, Any]:
    """Return the decision evidence stored on the first (summary) figure."""
    evidence: dict[str, Any] = result.figures[0].layout.meta["qubit_frequency_mapping"]
    return evidence


@pytest.mark.parametrize(
    ("moment_by_slot", "match"),
    [
        ({"RQ02": 2000.0}, "quality_level 2 is below 3"),
        ({"RQ02": 0.05}, "No readout candidate"),
        ({}, "No readout candidate"),
    ],
)
def test_absolute_quality_gate_still_applies(moment_by_slot, match) -> None:
    """Reject a best candidate below quality_level 3 or with no response at all."""
    result = _postprocess_with(_task_with_candidates(), _estimate(moment_by_slot))

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert match in result.validation_error


def test_unique_high_score_with_weak_secondary_is_selected() -> None:
    """Select the best candidate when its moment clears min_score_ratio over a weak runner-up."""
    result = _postprocess_with(
        _task_with_candidates(), _estimate({"RQ02": 10000.0, "RQ00": 1000.0})
    )

    assert result.validation_error is None
    assert result.output_parameters["resonator_candidate_index"].value == 2
    evidence = _evidence(result)
    assert evidence["outcome"] == "selected"
    assert evidence["ranking"] == [2, 0]
    assert evidence["runner_up"] == {"candidate_index": 0, "moment": 1000.0, "quality_level": 1}
    assert evidence["runner_up_status"] == "present"
    assert evidence["score_ratio"] == pytest.approx(10.0)


def test_zero_score_tie_cannot_publish_even_with_high_quality() -> None:
    """Reject zero-score ties even when the analysis reports passing quality."""
    result = _postprocess_with(
        _task_with_candidates(),
        _estimate({"RQ01": 0.0, "RQ02": 0.0}, quality_by_slot={"RQ01": 3, "RQ02": 3}),
    )

    assert result.output_parameters == {}
    assert "Ambiguous" in (result.validation_error or "")


def test_overflowing_ratio_retains_positive_runner_up_evidence() -> None:
    """Accept a separated finite score pair without misreporting its tiny runner-up."""
    result = _postprocess_with(_task_with_candidates(), _estimate({"RQ02": 1e308, "RQ00": 1e-308}))

    assert result.validation_error is None
    evidence = _evidence(result)
    assert evidence["runner_up_status"] == "present"
    assert evidence["score_ratio"] is None
    assert evidence["score_ratio_status"] == "overflow"
    assert "overflow" in evidence["reason"]
    assert "has moment 0" not in result.figures[0].to_json()
    assert "Infinity" not in result.figures[0].to_json()


def test_two_strong_similar_scores_are_rejected() -> None:
    """Reject two quality-passing candidates whose moments differ by less than the ratio."""
    result = _postprocess_with(
        _task_with_candidates(), _estimate({"RQ02": 10000.0, "RQ01": 6000.0})
    )

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "Ambiguous" in result.validation_error
    assert "min_score_ratio 2" in result.validation_error
    evidence = _evidence(result)
    assert evidence["outcome"] == "rejected"
    assert evidence["score_ratio"] == pytest.approx(10000.0 / 6000.0)
    assert evidence["proposal"]["resonator_candidate_index"] == 2
    assert evidence["proposal"]["published"] is False


def test_low_quality_runner_up_still_blocks_a_near_tie() -> None:
    """Count a low-quality runner-up so that it cannot hide a near-tie."""
    result = _postprocess_with(
        _task_with_candidates(),
        _estimate({"RQ02": 4000.0, "RQ03": 3000.0}, quality_by_slot={"RQ03": 2}),
    )

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "runner-up candidate 3" in result.validation_error


@pytest.mark.parametrize("order", [["RQ01", "RQ02"], ["RQ02", "RQ01"]])
def test_exact_tie_is_rejected_in_any_candidate_order(order) -> None:
    """Reject equal best moments whichever candidate comes first."""
    result = _postprocess_with(_task_with_candidates(), _estimate(dict.fromkeys(order, 10000.0)))

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "Ambiguous" in result.validation_error
    assert _evidence(result)["score_ratio"] == pytest.approx(1.0)
    assert _evidence(result)["ranking"] == [1, 2]


@pytest.mark.parametrize(
    "assignment",
    [
        {"RQ00": 12000.0, "RQ01": 3000.0, "RQ02": None, "RQ03": 500.0},
        {"RQ00": 500.0, "RQ01": None, "RQ02": 3000.0, "RQ03": 12000.0},
        {"RQ00": None, "RQ01": 12000.0, "RQ02": 500.0, "RQ03": 3000.0},
    ],
)
def test_selection_follows_the_score_not_the_candidate_order(assignment) -> None:
    """Select the highest moment wherever it sits in the candidate order."""
    expected = SLOTS.index(max((s for s in assignment if assignment[s]), key=assignment.get))

    result = _postprocess_with(_task_with_candidates(), _estimate(assignment))

    assert result.validation_error is None
    assert result.output_parameters["resonator_candidate_index"].value == expected
    assert _evidence(result)["score_ratio"] == pytest.approx(4.0)


@pytest.mark.parametrize(
    ("moment_by_slot", "status", "reason"),
    [
        ({"RQ02": 10000.0}, "absent", "only candidate with an f01 peak"),
        ({"RQ02": 10000.0, "RQ00": 0.0}, "zero", "zero moment"),
    ],
)
def test_absent_or_zero_runner_up_is_explicit_and_json_safe(moment_by_slot, status, reason) -> None:
    """Represent a missing or zero runner-up without an infinite ratio."""
    result = _postprocess_with(_task_with_candidates(), _estimate(moment_by_slot))

    assert result.validation_error is None
    evidence = _evidence(result)
    assert evidence["runner_up_status"] == status
    assert evidence["score_ratio"] is None
    assert reason in evidence["reason"]
    assert "Infinity" not in result.figures[0].to_json()
    assert "NaN" not in result.figures[0].to_json()


@pytest.mark.parametrize("bad_moment", [float("nan"), float("inf"), -1.0])
def test_non_finite_or_negative_scores_are_hard_failures(bad_moment) -> None:
    """Reject the whole result when any candidate reports an invalid moment."""
    result = _postprocess_with(
        _task_with_candidates(), _estimate({"RQ02": 10000.0, "RQ00": bad_moment})
    )

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "Invalid f01 moment" in result.validation_error
    row = _evidence(result)["candidates"][0]
    assert row["moment"] == (bad_moment if np.isfinite(bad_moment) else None)
    assert row["moment_raw"] == repr(bad_moment)
    assert result.figures[0].to_json().count("NaN") == 0


def test_failed_candidate_analysis_cannot_pass_with_a_clear_winner() -> None:
    """Reject when one candidate's analysis raises, however clear the best score is."""

    def estimate(fig, *args, **kwargs):
        if fig.layout.meta["readout_label"] == "RQ03":
            raise RuntimeError("labeling failed")
        return _estimate({"RQ02": 20000.0})(fig, *args, **kwargs)

    result = _postprocess_with(_task_with_candidates(), estimate)

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "analysis failed on [3]" in result.validation_error
    row = _evidence(result)["candidates"][3]
    assert row["status"] == "error"
    assert "labeling failed" in row["error"]


@pytest.mark.parametrize("ratio", [1.0, 0.5, float("nan"), float("inf"), True, "2"])
def test_invalid_min_score_ratio_is_rejected_before_hardware(ratio) -> None:
    """Reject a ratio that would accept ties or is not a finite number."""
    task = _task_with_candidates()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["min_score_ratio"].value = ratio

    with pytest.raises(ValueError, match="min_score_ratio"):
        _run(task, _single_response_result())


def test_min_score_ratio_is_configurable() -> None:
    """Apply a stricter ratio from the run parameter."""
    task = _task_with_candidates()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["min_score_ratio"].value = 5.0

    result = _postprocess_with(task, _estimate({"RQ02": 10000.0, "RQ00": 4000.0}))

    assert result.output_parameters == {}
    assert "below min_score_ratio 5" in (result.validation_error or "")
    assert _evidence(result)["rule"]["min_score_ratio"] == 5.0


def test_evidence_lists_every_candidate_for_review() -> None:
    """Record every candidate's raw scores, readout values, and the sweep on the summary."""
    result = _postprocess_with(
        _task_with_candidates(), _estimate({"RQ02": 10000.0, "RQ01": 1000.0})
    )

    evidence = _evidence(result)
    assert evidence["schema"] == "qdash.qubit_frequency_mapping.v1"
    assert evidence["rule"]["calibrated"] is False
    assert evidence["rule"]["min_quality_level"] == 3
    assert evidence["sweep"]["drive_frequency_ghz"]["points"] == len(DRIVE_FREQUENCIES)
    assert evidence["sweep"]["drive_power_db"]["start"] == DRIVE_POWERS[0]
    rows = evidence["candidates"]
    assert [row["candidate_index"] for row in rows] == [0, 1, 2, 3]
    assert [row["readout_label"] for row in rows] == SLOTS
    assert [row["readout_frequency"] for row in rows] == READOUT_FREQUENCIES
    assert [row["readout_power_db"] for row in rows] == pytest.approx(
        [20 * np.log10(a) for a in READOUT_AMPLITUDES]
    )
    assert [row["status"] for row in rows] == [
        "no_f01_peak",
        "f01_detected",
        "f01_detected",
        "no_f01_peak",
    ]
    assert [row["moment"] for row in rows] == [None, 1000.0, 10000.0, None]
    assert [row["rank"] for row in rows] == [None, 2, 1, None]
    assert [row["selected"] for row in rows] == [False, False, True, False]
    assert evidence["proposal"]["published"] is True
    assert evidence["proposal"]["coarse_control_amplitude"] == pytest.approx(
        result.output_parameters["coarse_control_amplitude"].value
    )


def test_detection_below_minimum_qubit_frequency_is_rejected() -> None:
    """Apply the existing 2.5 GHz lower bound to the selected response."""
    task = _task_with_candidates()
    run_result, _ = _run(task, _tagged_result())

    def estimate(fig, *_args, **_kwargs):
        f01 = (
            SimpleNamespace(frequency=2.0, repr_db=-30.0, quality_level=5, moment=20000.0)
            if fig.layout.meta["readout_label"] == "RQ02"
            else None
        )
        return go.Figure(fig), SimpleNamespace(f01=f01, f12=None, anharmonicity=None)

    with patch(f"{MODULE}.estimate_and_mark_qubit_figure", side_effect=estimate):
        result = _postprocess(task, run_result)

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "2.5 GHz" in result.validation_error


def test_analysis_uses_the_existing_spectroscopy_configuration() -> None:
    """Analyze every candidate with the qubit spectroscopy config and trim retry."""
    task = _task_with_candidates()
    run_result, _ = _run(task, _tagged_result())
    estimate = MagicMock(side_effect=_estimate({"RQ02": 10000.0}))

    with patch(f"{MODULE}.estimate_and_mark_qubit_figure", estimate):
        result = _postprocess(task, run_result)

    assert result.validation_error is None
    assert estimate.call_count == len(SLOTS)
    for call in estimate.call_args_list:
        assert call.args[1] is task._analysis_config
        assert call.kwargs == {"retry_with_trim": True}


def _producer_database_record(assignment_order: list[int | float]) -> dict[str, dict[str, Any]]:
    """Run the producer postprocess and store its outputs as a calibration record."""
    producer = CheckResonatorSpectroscopy()
    producer.run_parameters = copy.deepcopy(producer.run_parameters)
    producer._bare_shift_estimator_type = "config"
    producer.run_parameters["detection_only"].value = True
    producer.run_parameters["resonator_assignment_order"].value = assignment_order
    raw_fig = go.Figure(
        go.Heatmap(x=[10.2, 10.3, 10.4, 10.5], y=[-60.0, -40.0], z=[[0.0] * 4, [0.0] * 4])
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i, y=1, prominence=1.0))
        for i in range(4)
    ]
    producer_module = "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
    with (
        patch.object(producer, "_prepare_analysis_figure", return_value=raw_fig),
        patch(
            producer_module + "estimate_resonator_frequency_from_figure",
            return_value=(resonances, [], [10.43, 10.21, 10.36, 10.29]),
        ),
        patch(producer_module + "estimate_minimum_usable_power", return_value=-40.0),
        patch(
            producer_module + "estimate_optimal_powers",
            return_value=[-26.0, -34.0, -28.0, -30.0],
        ),
        patch(producer_module + "create_marked_figure", return_value=raw_fig),
    ):
        produced = producer.postprocess(
            MagicMock(), "exec-resonator", RunResult(raw_result={"fig": raw_fig}), "1"
        )
    assert produced.validation_error is None
    return {
        name: {**value.model_dump(), "task_id": "task-resonator"}
        for name, value in produced.output_parameters.items()
    }


@pytest.mark.parametrize("assignment_order", [[3, 0, 2, 1], [0, 1, 2, 3]])
def test_producer_candidates_resolve_into_consumer_inputs(assignment_order) -> None:
    """Hand the detection-only candidates to the consumer whatever the assignment order."""
    record = _producer_database_record(assignment_order)
    task = CheckQubitFrequencyMapping()
    task.input_parameters = copy.deepcopy(task.input_parameters)

    task._populate_parameters({"": [record], "self": [record]})
    candidates = task._candidate_set()

    assert [candidate.frequency for candidate in candidates] == [10.21, 10.29, 10.36, 10.43]
    assert [candidate.readout_amplitude for candidate in candidates] == pytest.approx(
        [10 ** (power / 20) for power in (-34.0, -30.0, -28.0, -26.0)]
    )
    assert [candidate.index for candidate in candidates] == [0, 1, 2, 3]


def _shifted_axis_result(shift: float) -> SimpleNamespace:
    """Return a result whose drive-frequency axes are all shifted by the same amount."""
    result = _single_response_result("RQ02")
    shifted = DRIVE_FREQUENCIES + shift
    result.data["frequency_range"] = shifted
    for candidate in result.data["candidates"].values():
        candidate["frequency_range"] = shifted
    for fig in result.figures.values():
        fig.data[0].x = shifted
    return result


def test_consistently_shifted_axes_do_not_match_the_requested_sweep() -> None:
    """Reject same-shape axes that differ from the sweep the task requested."""
    task = _task_with_candidates()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["frequency_range"].value = (4.0, 4.5, 0.005)
    run_result, _ = _run(task, _shifted_axis_result(0.25))

    result = _postprocess(task, run_result)

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "requested sweep" in result.validation_error


def test_requested_sweep_is_accepted_when_the_axes_match() -> None:
    """Publish when the measured axes equal the requested sweep."""
    task = _task_with_candidates()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["frequency_range"].value = (4.0, 4.5, 0.005)
    run_result, _ = _run(task, _shifted_axis_result(0.0))

    result = _postprocess(task, run_result)

    assert result.validation_error is None
    assert result.output_parameters["coarse_qubit_frequency"].value == pytest.approx(
        DRIVE_FREQUENCIES[RESPONSE_INDEX]
    )


def _raw_figures(result) -> dict[str, go.Figure]:
    return {
        fig.layout.meta["readout_label"]: fig
        for fig in result.figures
        if fig.layout.meta and len(fig.data) == 1
    }


def test_swapped_display_figures_do_not_change_the_selection() -> None:
    """Analyze each candidate's own phase data even when Qubex's figures are swapped."""
    task = _task_with_candidates()
    contrib_result = _single_response_result("RQ02")
    figures = contrib_result.figures
    figures["RQ01"], figures["RQ02"] = figures["RQ02"], figures["RQ01"]
    run_result, _ = _run(task, contrib_result)

    result = _postprocess(task, run_result)

    assert result.validation_error is None
    assert result.output_parameters["resonator_candidate_index"].value == 2
    assert result.output_parameters["resonator_frequency"].value == READOUT_FREQUENCIES[2]
    raw = _raw_figures(result)
    for index, slot in enumerate(SLOTS):
        assert raw[slot].layout.meta["candidate_index"] == index
        assert np.array_equal(
            np.asarray(raw[slot].data[0].z), contrib_result.data["candidates"][slot]["phases"]
        )


@pytest.mark.parametrize(
    "corrupt_figures",
    [
        lambda figures: figures["RQ02"].data[0].update(z=np.zeros_like(figures["RQ02"].data[0].z)),
        lambda figures: figures["RQ02"].data[0].update(x=DRIVE_FREQUENCIES + 0.3),
        lambda figures: figures["RQ00"].data[0].update(z=_response_z(RESPONSE_INDEX + 20)),
        lambda figures: figures.clear(),
    ],
)
def test_display_figures_are_never_an_analysis_source(corrupt_figures) -> None:
    """Publish the data-derived frequency whatever the Qubex display figures contain."""
    task = _task_with_candidates()
    contrib_result = _single_response_result("RQ02")
    corrupt_figures(contrib_result.figures)
    run_result, _ = _run(task, contrib_result)

    result = _postprocess(task, run_result)

    assert result.validation_error is None
    assert result.output_parameters["resonator_candidate_index"].value == 2
    assert result.output_parameters["coarse_qubit_frequency"].value == pytest.approx(
        DRIVE_FREQUENCIES[RESPONSE_INDEX]
    )


def test_swapped_candidate_payloads_are_rejected() -> None:
    """Reject payloads stored under another candidate's readout slot."""
    task = _task_with_candidates()
    contrib_result = _single_response_result("RQ02")
    candidates = contrib_result.data["candidates"]
    candidates["RQ01"], candidates["RQ02"] = candidates["RQ02"], candidates["RQ01"]
    run_result, _ = _run(task, contrib_result)

    result = _postprocess(task, run_result)

    assert result.output_parameters == {}
    assert result.validation_error is not None
    assert "readout_label" in result.validation_error


_T0 = datetime(2026, 11, 17, 9, 0, 0)


def _attempt(
    qid: str,
    execution_id: str,
    *,
    task_id: str | None = None,
    status: str = "completed",
    minutes: float | None = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=task_id or f"{execution_id}-{qid}",
        execution_id=execution_id,
        qid=qid,
        status=status,
        start_at=None if minutes is None else _T0 + timedelta(minutes=minutes),
    )


def _mux_attempts(execution_id: str, minutes: float, **overrides: str) -> list[SimpleNamespace]:
    return [
        _attempt(qid, execution_id, status=overrides.get(f"q{qid}", "completed"), minutes=minutes)
        for qid in ("0", "1", "2", "3")
    ]


def _source_error(attempts, qid: str = "1", execution_id: str = "exec-A") -> str | None:
    return candidate_source_error(
        attempts, qid=qid, execution_id=execution_id, task_id=f"{execution_id}-{qid}"
    )


def test_complete_latest_attempt_is_an_accepted_source() -> None:
    """Accept the candidate set of a complete attempt that no other attempt followed."""
    attempts = [*_mux_attempts("exec-old", -60, q0="failed"), *_mux_attempts("exec-A", 0)]

    assert _source_error(attempts) is None


@pytest.mark.parametrize("status", ["failed", "completed", "running", "skipped"])
def test_any_newer_attempt_in_the_mux_invalidates_the_source(status) -> None:
    """Reject the set after any later attempt in the MUX, whatever its outcome."""
    attempts = [*_mux_attempts("exec-A", 0), _attempt("3", "exec-B", status=status, minutes=5)]

    error = _source_error(attempts)

    assert error is not None
    assert "exec-B" in error


def test_attempt_with_an_unknown_start_invalidates_the_source() -> None:
    """Treat another execution's attempt without a start time as newer."""
    attempts = [*_mux_attempts("exec-A", 0), _attempt("0", "exec-B", minutes=None)]

    assert _source_error(attempts) is not None


@pytest.mark.parametrize("failed_qid", ["0", "1", "3"])
def test_partial_source_attempt_is_rejected(failed_qid) -> None:
    """Reject a set whose own attempt did not complete for every recorded qid of the MUX."""
    attempts = _mux_attempts("exec-A", 0, **{f"q{failed_qid}": "failed"})

    error = _source_error(attempts)

    assert error is not None
    assert f"qid={failed_qid}" in error


def test_rerun_in_the_same_execution_invalidates_the_first_result() -> None:
    """Reject a result that a later run of the same execution superseded."""
    attempts = [*_mux_attempts("exec-A", 0), _attempt("1", "exec-A", task_id="rerun", minutes=3)]

    assert "ran again" in (_source_error(attempts) or "")


@pytest.mark.parametrize(
    ("attempts", "match"),
    [
        ([], "no CheckResonatorSpectroscopy task result"),
        ([_attempt("1", "exec-other", task_id="exec-A-1")], "belongs to execution"),
        ([_attempt("2", "exec-A", task_id="exec-A-1")], "is for qid=2"),
    ],
)
def test_source_must_match_the_recorded_result(attempts, match) -> None:
    """Require the recorded task result of the candidate set for this qid and execution."""
    assert match in (_source_error(attempts) or "")


class _SyntheticMeasurement:
    """Stand-in measurement service: every readout returns noise except one responding slot."""

    def __init__(self, responding_qubit: str) -> None:
        self.responding_qubit = responding_qubit
        self.calls = 0
        self.rng = np.random.default_rng(7)

    def execute(self, *, frequencies: dict[str, float], **_kwargs: Any) -> SimpleNamespace:
        power = DRIVE_POWERS[self.calls // len(DRIVE_FREQUENCIES)]
        point = self.calls % len(DRIVE_FREQUENCIES)
        self.calls += 1
        half_width = int((power + 35.0) / 5.0)
        data = {}
        for qubit in ("Q00", "Q01", "Q02", "Q03"):
            phase = self.rng.normal(0.0, 0.05)
            if qubit == self.responding_qubit and power >= -35.0:
                if abs(point - RESPONSE_INDEX) <= half_width:
                    phase = 2.5
            data[qubit] = [SimpleNamespace(kerneled=np.exp(1j * phase))]
        return SimpleNamespace(data=data)


def _offline_experiment(responding_qubit: str) -> MagicMock:
    """Return an Experiment double that lets the installed helper run without hardware."""
    from contextlib import nullcontext

    exp = _experiment()
    exp.ctx.resolve_qubit_label.side_effect = lambda label: (
        label if label.startswith("Q") else "Q" + label[2:]
    )
    exp.ctx.resolve_read_label.side_effect = lambda label: label
    exp.ctx.params.readout_amplitude = {}
    exp.ctx.system_manager.plan_frequency_sweep.side_effect = lambda _q, freqs, **_k: [
        SimpleNamespace(configuration=None, indices=range(len(freqs)), values=freqs)
    ]
    exp.ctx.system_manager.modified_sweep_configuration.side_effect = lambda _c: nullcontext()
    exp.measurement_service = _SyntheticMeasurement(responding_qubit)
    return exp


def test_installed_qubex_provides_the_helper_with_the_called_signature() -> None:
    """Bind the arguments the task passes to the helper of the pinned Qubex revision."""
    import inspect

    helper = load_multiplexed_readout_qubit_spectroscopy()
    task = _task_with_candidates()
    _, recorded = _run(task, _single_response_result())

    assert helper.__module__.startswith("qubex.contrib")
    inspect.signature(helper).bind(*recorded.call_args.args, **recorded.call_args.kwargs)


def test_installed_qubex_helper_result_selects_the_responding_candidate() -> None:
    """Run the installed helper offline and select from its real result end to end."""
    task = _task_with_candidates()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["frequency_range"].value = (4.0, 4.5, 0.005)
    exp = _offline_experiment("Q02")

    with (
        patch.object(task, "get_experiment", return_value=exp),
        patch.object(task, "get_qubit_label", return_value="Q01"),
        patch.object(task, "_verify_candidate_source"),
    ):
        run_result = task.run(cast("QubexBackend", object()), "1")
    result = _postprocess(task, run_result)

    assert result.validation_error is None
    assert result.output_parameters["resonator_candidate_index"].value == 2
    assert result.output_parameters["coarse_qubit_frequency"].value == pytest.approx(
        DRIVE_FREQUENCIES[RESPONSE_INDEX]
    )
    evidence = _evidence(result)
    assert evidence["runner_up_status"] == "absent"
    assert [row["status"] for row in evidence["candidates"]] == [
        "no_f01_peak",
        "no_f01_peak",
        "f01_detected",
        "no_f01_peak",
    ]
    assert evidence["candidates"][2]["selected"] is True
