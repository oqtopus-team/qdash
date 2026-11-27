"""Tests for the MUX-level CheckResonatorQubitMapping task."""

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import numpy as np
import pytest

import qdash.workflow.calibtasks.qubex as qubex_tasks
from qdash.common.config.backend import get_tasks
from qdash.common.mux_mapping import MuxMapping
from qdash.workflow.calibtasks.active_protocols import is_mux_task
from qdash.workflow.calibtasks.qubex.cw.check_resonator_qubit_mapping import (
    CheckResonatorQubitMapping,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any

FREQUENCY_RANGE = (3.0, 5.75, 0.02)
# Provisional readout settings written by CheckResonatorSpectroscopy, in qid order.
StoredReadout = tuple[float, float, float | None]
STORED: dict[str, StoredReadout] = {
    "0": (10.10, 0.10, -20.0),
    "1": (10.20, 0.11, -19.0),
    "2": (10.30, 0.12, -18.0),
    "3": (10.40, 0.13, -17.0),
}
# True owner of each stored resonator: the stored order is wrong for Q00 and Q01.
TRUE_RESONATOR = {"Q00": 10.20, "Q01": 10.10, "Q02": 10.30, "Q03": 10.40}
F01 = {"Q00": 4.0, "Q01": 4.3, "Q02": 4.6, "Q03": 5.0}


class FakeExperiment:
    """Qubit spectroscopy that responds only when reading out the qubit's resonator."""

    def __init__(
        self,
        responses: dict[tuple[str, float], float] | None = None,
        qubit_labels: list[str] | None = None,
    ) -> None:
        if responses is None:
            responses = dict.fromkeys(TRUE_RESONATOR.items(), 0.5)
        self.responses = responses
        self.qubit_labels = qubit_labels or ["Q00", "Q01", "Q02", "Q03"]
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.calib_note = MagicMock()
        self._rng = np.random.default_rng(7)

    def get_qubit_label(self, index: int) -> str:
        return f"Q{index:02d}"

    def modified_frequencies(self, _overrides: dict[str, float]) -> Any:
        return nullcontext()

    def qubit_spectroscopy(self, target: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((target, kwargs))
        frequencies = np.asarray(kwargs["frequency_range"], dtype=float)
        phases = self._rng.normal(0.0, 0.02, frequencies.size)
        height = self.responses.get((target, round(kwargs["readout_frequency"], 6)), 0.0)
        phases += height / (1.0 + ((frequencies - F01[target]) / 0.05) ** 2)
        powers = np.asarray(kwargs["power_range"], dtype=float)
        return {
            "frequency_range": frequencies,
            "power_range": powers,
            "data": np.tile(phases, (powers.size, 1)),
        }


def _stored_entry(frequency: float, amplitude: float, power: float | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "readout_frequency": {"value": frequency},
        "resonator_frequency": {"value": frequency},
        "readout_amplitude": {"value": amplitude},
    }
    if power is not None:
        entry["optimal_power"] = {"value": power}
    return entry


def _make_task(
    monkeypatch: pytest.MonkeyPatch,
    exp: FakeExperiment,
    stored: dict[str, StoredReadout] | None = None,
) -> tuple[CheckResonatorQubitMapping, QubexBackend]:
    entries: dict[str, StoredReadout] = STORED if stored is None else stored
    task = CheckResonatorQubitMapping()
    task.run_parameters["frequency_range"].value = FREQUENCY_RANGE
    rep = entries.get("0")
    if rep is not None:
        task.input_parameters["readout_frequency"].value = rep[0]
        task.input_parameters["readout_amplitude"].value = rep[1]
    backend = cast(
        "QubexBackend",
        SimpleNamespace(config={}, ensure_mux_mapping_compatible=MuxMapping.legacy),
    )
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(
        task,
        "_stored_calibration",
        lambda _backend, qid: _stored_entry(*entries[qid]) if qid in entries else {},
    )
    return task, backend


def test_measures_every_pair_one_at_a_time_at_high_power(monkeypatch) -> None:
    exp = FakeExperiment()
    task, backend = _make_task(monkeypatch, exp)

    task.run(backend, "0")

    assert len(exp.calls) == 16
    pairs = {(target, kwargs["readout_frequency"]) for target, kwargs in exp.calls}
    assert len(pairs) == 16
    for target, kwargs in exp.calls:
        assert isinstance(target, str)  # one qubit per call: no multiplexing
        np.testing.assert_array_equal(kwargs["power_range"], [0.0])
        assert np.diff(kwargs["frequency_range"]) == pytest.approx(0.02)
        assert kwargs["plot"] is False
        assert kwargs["save_image"] is False
        assert kwargs["n_shots"] == 512
        assert kwargs["shot_interval"] == 1024.0
        assert kwargs["simultaneous_drive"] is True
        stored = {values[0]: values[1] for values in STORED.values()}
        assert kwargs["readout_amplitude"] == stored[kwargs["readout_frequency"]]
    exp.calib_note.save.assert_called_once()


def test_postprocess_publishes_swapped_readout_parameters(monkeypatch) -> None:
    exp = FakeExperiment()
    task, backend = _make_task(monkeypatch, exp)
    run_result = task.run(backend, "0")

    published = {}
    for qid in ("0", "1", "2", "3"):
        result = task.postprocess(backend, "exec-1", run_result, qid)
        assert result.validation_error is None
        assert len(result.figures) == 1
        published[qid] = {name: param.value for name, param in result.output_parameters.items()}
        assert all(p.execution_id == "exec-1" for p in result.output_parameters.values())

    assert published["0"] == {
        "resonator_frequency": 10.20,
        "readout_amplitude": 0.11,
        "optimal_power": -19.0,
    }
    assert published["1"] == {
        "resonator_frequency": 10.10,
        "readout_amplitude": 0.10,
        "optimal_power": -20.0,
    }
    assert published["2"]["resonator_frequency"] == 10.30
    assert published["3"]["resonator_frequency"] == 10.40
    assert task.output_spec["resonator_frequency"].publish_targets == (
        "resonator_frequency",
        "readout_frequency",
    )


def test_unverified_qubits_get_validation_error_and_no_outputs(monkeypatch) -> None:
    responses = {
        ("Q00", 10.20): 0.5,
        ("Q01", 10.10): 0.5,
        # Q02 responds equally at two candidates; Q03 never responds.
        ("Q02", 10.30): 0.5,
        ("Q02", 10.40): 0.5,
    }
    exp = FakeExperiment(responses)
    task, backend = _make_task(monkeypatch, exp)
    run_result = task.run(backend, "0")

    ambiguous = task.postprocess(backend, "exec-1", run_result, "2")
    silent = task.postprocess(backend, "exec-1", run_result, "3")
    mapped = task.postprocess(backend, "exec-1", run_result, "0")

    assert ambiguous.output_parameters == {}
    assert ambiguous.validation_error is not None
    assert "ambiguous" in ambiguous.validation_error
    assert len(ambiguous.figures) == 1
    assert silent.output_parameters == {}
    assert silent.validation_error is not None
    assert "no_response" in silent.validation_error
    assert mapped.validation_error is None
    assert mapped.output_parameters["resonator_frequency"].value == 10.20


def test_candidate_without_optimal_power_publishes_frequency_and_amplitude(monkeypatch) -> None:
    stored = dict(STORED)
    stored["1"] = (10.20, 0.11, None)
    exp = FakeExperiment()
    task, backend = _make_task(monkeypatch, exp, stored)

    result = task.postprocess(backend, "exec-1", task.run(backend, "0"), "0")

    assert set(result.output_parameters) == {"resonator_frequency", "readout_amplitude"}


def test_complex_trace_is_converted_to_phase() -> None:
    phases = np.array([0.1, -0.4, 1.2, 3.0])
    result = {"frequency_range": [4.0, 4.02, 4.04, 4.06], "data": [np.exp(1j * phases)]}

    frequencies, extracted = CheckResonatorQubitMapping._extract_1d_trace(result)

    np.testing.assert_allclose(frequencies, [4.0, 4.02, 4.04, 4.06])
    np.testing.assert_allclose(extracted, phases)
    assert extracted.dtype == np.float64


def test_real_trace_and_phases_key_are_read_directly() -> None:
    result = {"frequency_range": [4.0, 4.02], "phases": [0.5, -0.5]}

    _frequencies, extracted = CheckResonatorQubitMapping._extract_1d_trace(result)

    np.testing.assert_allclose(extracted, [0.5, -0.5])


def test_does_not_publish_qubit_frequency_outputs() -> None:
    assert {"coarse_qubit_frequency", "f01", "qubit_frequency"}.isdisjoint(
        CheckResonatorQubitMapping.output_spec
    )
    publish_targets = {
        target
        for spec in CheckResonatorQubitMapping.output_spec.values()
        for target in spec.publish_targets
    }
    assert "control_frequency" not in publish_targets


def test_representative_uses_resolved_inputs(monkeypatch) -> None:
    exp = FakeExperiment({("Q00", 10.15): 0.5, ("Q01", 10.20): 0.5})
    task, backend = _make_task(monkeypatch, exp)
    task.input_parameters["readout_frequency"].value = 10.15  # explicit override

    task.run(backend, "0")

    assert 10.15 in {kwargs["readout_frequency"] for _target, kwargs in exp.calls}
    assert 10.10 not in {kwargs["readout_frequency"] for _target, kwargs in exp.calls}


def test_duplicate_and_missing_candidates_are_dropped(monkeypatch) -> None:
    stored: dict[str, StoredReadout] = {
        "0": (10.10, 0.10, -20.0),
        "1": (10.1002, 0.11, -19.0),  # same resonator stored twice
        "2": (10.30, 0.12, -18.0),
    }
    exp = FakeExperiment({("Q00", 10.10): 0.5, ("Q02", 10.30): 0.5})
    task, backend = _make_task(monkeypatch, exp, stored)

    run_result = task.run(backend, "0")

    mapping = run_result.raw_result["mapping"]
    assert [c.frequency for c in mapping.candidates] == [10.10, 10.30]
    assert [c.source_qid for c in mapping.candidates] == ["0", "2"]
    assert len(exp.calls) == 8


def test_fewer_than_two_candidates_fails_before_measuring(monkeypatch) -> None:
    exp = FakeExperiment()
    task, backend = _make_task(monkeypatch, exp, {"0": (10.10, 0.10, -20.0)})

    with pytest.raises(ValueError, match="at least 2 resonator candidates"):
        task.run(backend, "0")
    assert exp.calls == []


def test_unloaded_qubit_is_not_measured_and_fails_postprocess(monkeypatch) -> None:
    exp = FakeExperiment(qubit_labels=["Q00", "Q01", "Q02"])
    task, backend = _make_task(monkeypatch, exp)

    run_result = task.run(backend, "0")
    result = task.postprocess(backend, "exec-1", run_result, "3")

    assert len(exp.calls) == 12
    assert result.output_parameters == {}
    assert result.validation_error == "Resonator mapping did not measure qid=3"


def test_positive_drive_power_is_rejected_before_measuring(monkeypatch) -> None:
    exp = FakeExperiment()
    task, backend = _make_task(monkeypatch, exp)
    task.run_parameters["drive_power"].value = 3.0

    with pytest.raises(ValueError, match="drive_power"):
        task.run(backend, "0")
    assert exp.calls == []


def test_frequency_range_is_resolved_from_control_box_with_coarse_step(monkeypatch) -> None:
    task = CheckResonatorQubitMapping()
    exp = MagicMock()
    exp.readout_duration = 1024.0
    exp.ctx.experiment_system.get_control_box_for_qubit.return_value = SimpleNamespace(
        traits=SimpleNamespace(default_control_frequency_range=(3.0, 5.75, 0.005))
    )
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    task.resolve_run_parameters(cast("QubexBackend", object()), "0")

    assert task.run_parameters["frequency_range"].value == (3.0, 5.75, 0.02)
    exp.ctx.experiment_system.get_control_box_for_qubit.assert_called_once_with("Q00")


def test_explicit_frequency_range_is_kept(monkeypatch) -> None:
    task = CheckResonatorQubitMapping()
    task.run_parameters["frequency_range"].value = (4.0, 5.0, 0.01)
    monkeypatch.setattr(task, "get_experiment", lambda _backend: MagicMock())

    task.resolve_run_parameters(cast("QubexBackend", object()), "0")

    assert task.run_parameters["frequency_range"].value == (4.0, 5.0, 0.01)


def test_mux_members_come_from_pinned_mapping(monkeypatch) -> None:
    exp = FakeExperiment(qubit_labels=["Q04", "Q05", "Q06", "Q07"])
    task, _backend = _make_task(monkeypatch, exp)
    mapping = MuxMapping.from_groups({1: ["4", "5", "6", "7"]})
    backend = cast("QubexBackend", SimpleNamespace(ensure_mux_mapping_compatible=lambda: mapping))

    assert task._mux_qids(backend, "6") == ["4", "5", "6", "7"]


def test_task_is_registered_in_catalog_and_backend() -> None:
    assert CheckResonatorQubitMapping.is_mux_level is True
    assert CheckResonatorQubitMapping.task_type == "qubit"
    assert "CheckResonatorQubitMapping" in qubex_tasks.__all__
    assert is_mux_task("CheckResonatorQubitMapping", "qubex")
    assert "CheckResonatorQubitMapping" in get_tasks("qubex")

    catalog_path = Path(qubex_tasks.__file__).parent.parent / "task_catalog.json"
    catalog = json.loads(catalog_path.read_text())
    assert "CheckResonatorQubitMapping" in json.dumps(catalog)
