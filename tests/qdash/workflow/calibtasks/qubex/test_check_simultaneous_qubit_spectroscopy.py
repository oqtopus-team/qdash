from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.cw.check_simultaneous_qubit_spectroscopy import (
    CheckSimultaneousQubitSpectroscopy,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any


def test_batch_run_calls_contrib_helper_with_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    task = CheckSimultaneousQubitSpectroscopy()
    calls: dict[str, Any] = {}

    def helper(
        exp: Any,
        *,
        targets: list[str],
        frequency_range: Any,
        power_range: Any,
        readout_amplitudes: dict[str, float] | None,
        readout_frequencies: dict[str, float] | None,
        shots: int,
        interval: int,
        plot: bool,
        save_image: bool,
    ) -> dict[str, Any]:
        calls.update(
            {
                "experiment": exp,
                "targets": targets,
                "frequency_range": frequency_range,
                "power_range": power_range,
                "readout_amplitudes": readout_amplitudes,
                "readout_frequencies": readout_frequencies,
                "shots": shots,
                "interval": interval,
                "plot": plot,
                "save_image": save_image,
            }
        )
        return {"Q00": {"fig": "fig-0"}, "Q01": {"fig": "fig-1"}}

    backend = SimpleNamespace(config={"chip_id": "144Q-test"})
    experiment = object()

    monkeypatch.setattr(task, "get_experiment", lambda _backend: experiment)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, qid: f"Q{int(qid):02d}")
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.cw.check_simultaneous_qubit_spectroscopy."
        "simultaneous_qubit_spectroscopy",
        helper,
    )

    result = task.batch_run(cast("QubexBackend", backend), ["0", "1"])

    assert isinstance(result, RunResult)
    assert result.raw_result == {"Q00": {"fig": "fig-0"}, "Q01": {"fig": "fig-1"}}
    assert calls["experiment"] is experiment
    assert calls["targets"] == ["Q00", "Q01"]
    assert calls["frequency_range"][0] == pytest.approx(3.0)
    assert calls["power_range"][0] == pytest.approx(-40.0)
    assert calls["power_range"][1] == pytest.approx(-35.0)
    assert calls["power_range"][-1] == pytest.approx(-5.0)
    assert calls["readout_amplitudes"] is None
    assert calls["readout_frequencies"] is None
    assert calls["shots"] == 1024
    assert isinstance(calls["interval"], int)
    assert calls["plot"] is False
    assert calls["save_image"] is False


def test_batch_run_builds_readout_maps_from_calibration_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = CheckSimultaneousQubitSpectroscopy()
    calls: dict[str, Any] = {}

    calibration_data = {
        "0": {
            "readout_amplitude": {"value": 0.017},
            "readout_frequency": {"value": 6.123},
        },
        "1": {
            "readout_amplitude": {"value": 0.019},
            "readout_frequency": {"value": 6.456},
        },
    }

    class FakeQubitRepository:
        def get_calibration_data(
            self, *, project_id: str, chip_id: str, qid: str
        ) -> dict[str, Any]:
            assert project_id == "project-1"
            assert chip_id == "144Q-test"
            return calibration_data[qid]

    def helper(
        _exp: Any,
        *,
        targets: list[str],
        readout_amplitudes: dict[str, float] | None,
        readout_frequencies: dict[str, float] | None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        calls.update(
            {
                "targets": targets,
                "readout_amplitudes": readout_amplitudes,
                "readout_frequencies": readout_frequencies,
            }
        )
        return {"Q00": {"fig": "fig-0"}, "Q01": {"fig": "fig-1"}}

    backend = SimpleNamespace(config={"chip_id": "144Q-test", "project_id": "project-1"})

    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, qid: f"Q{int(qid):02d}")
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.cw.check_simultaneous_qubit_spectroscopy."
        "MongoQubitCalibrationRepository",
        FakeQubitRepository,
    )
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.cw.check_simultaneous_qubit_spectroscopy."
        "simultaneous_qubit_spectroscopy",
        helper,
    )

    result = task.batch_run(cast("QubexBackend", backend), ["0", "1"])

    assert result.raw_result == {"Q00": {"fig": "fig-0"}, "Q01": {"fig": "fig-1"}}
    assert calls["targets"] == ["Q00", "Q01"]
    assert calls["readout_amplitudes"] == {"Q00": 0.017, "Q01": 0.019}
    assert calls["readout_frequencies"] == {"Q00": 6.123, "Q01": 6.456}


def test_single_run_passes_loaded_readout_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    task = CheckSimultaneousQubitSpectroscopy()
    task.input_parameters["readout_amplitude"] = ParameterModel(value=0.017, unit="a.u.")
    task.input_parameters["readout_frequency"] = ParameterModel(value=6.123, unit="GHz")
    calls: dict[str, Any] = {}

    def helper(
        _exp: Any,
        *,
        targets: list[str],
        readout_amplitudes: dict[str, float] | None,
        readout_frequencies: dict[str, float] | None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        calls.update(
            {
                "targets": targets,
                "readout_amplitudes": readout_amplitudes,
                "readout_frequencies": readout_frequencies,
            }
        )
        return {"Q00": {"fig": "fig-0"}}

    backend = SimpleNamespace(config={"chip_id": "144Q-test"})

    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.cw.check_simultaneous_qubit_spectroscopy."
        "simultaneous_qubit_spectroscopy",
        helper,
    )

    result = task.run(cast("QubexBackend", backend), "0")

    assert result.raw_result == {"Q00": {"fig": "fig-0"}}
    assert calls["targets"] == ["Q00"]
    assert calls["readout_amplitudes"] == {"Q00": 0.017}
    assert calls["readout_frequencies"] == {"Q00": 6.123}


def test_normalize_single_result_for_single_label() -> None:
    result = CheckSimultaneousQubitSpectroscopy._normalize_results(
        {"Q00": {"fig": "fig-0"}}, ["Q00"]
    )

    assert result == {"Q00": {"fig": "fig-0"}}


def test_normalize_result_object_with_label_keyed_data() -> None:
    raw_result = SimpleNamespace(data={"Q00": {"fig": "fig-0"}, "Q01": {"fig": "fig-1"}})

    result = CheckSimultaneousQubitSpectroscopy._normalize_results(raw_result, ["Q00", "Q01"])

    assert result == {"Q00": {"fig": "fig-0"}, "Q01": {"fig": "fig-1"}}


def test_normalize_rejects_unkeyed_result() -> None:
    with pytest.raises(ValueError, match="not keyed by qubit label"):
        CheckSimultaneousQubitSpectroscopy._normalize_results({"fig": "combined"}, ["Q00"])
