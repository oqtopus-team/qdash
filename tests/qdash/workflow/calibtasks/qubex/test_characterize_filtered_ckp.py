from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import plotly.graph_objects as go
import pytest
import qubex

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.measurement.characterize_filtered_ckp import (
    CharacterizeFilteredCKP,
)
from qdash.workflow.engine.progress import ProgressPlan


def test_rabi_distance_accepts_signed_iq_offset() -> None:
    """Rabi distance is an IQ offset, whose sign depends on the IQ origin."""
    assert CharacterizeFilteredCKP.input_spec["rabi_angle"].unit == "rad"
    CharacterizeFilteredCKP.input_spec["rabi_distance"].validate_effective_value(
        "rabi_distance", -0.10508421819865316
    )


@pytest.fixture
def filtered_ckp(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    task = CharacterizeFilteredCKP()
    task.input_parameters["qubit_frequency"] = InputParameterModel(value=5.1, unit="GHz")
    task.input_parameters["readout_frequency"] = InputParameterModel(value=6.2, unit="GHz")
    task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.2, unit="a.u.")
    task.run_parameters["qubit_detuning_range"].value = [-0.02, 0.0, 0.02]
    task.run_parameters["resonator_detuning_range"].value = [-0.1, 0.0, 0.1]

    active_frequencies: dict[str, float] = {}

    @contextmanager
    def modified_frequencies(frequencies: dict[str, float]) -> Iterator[None]:
        active_frequencies.update(frequencies)
        try:
            yield
        finally:
            active_frequencies.clear()

    params = SimpleNamespace(readout_amplitude={"Q00": 0.3})
    system_manager = SimpleNamespace(modified_backend_settings=MagicMock())
    exp = SimpleNamespace(
        params=params,
        modified_frequencies=modified_frequencies,
        # A real experiment exposes these attributes.  Keeping them on the
        # fixture verifies that CKP does not accidentally use the common
        # helper which reconfigures QuEL1 mixer and capture hardware.
        ctx=SimpleNamespace(),
        system_manager=system_manager,
    )
    figures = {
        name: go.Figure()
        for name in (
            "ckp_fit",
            "ckp_heatmap_g",
            "ckp_heatmap_e",
            "readout_optimization",
        )
    }
    result = SimpleNamespace(
        data={
            "omega_r_g": 6.15,
            "omega_p": 6.23,
            "J": 0.012,
            "kappa": 0.045,
            "chi": -0.0015,
            "n_crit": 22.0,
            "optimal_readout_frequency": 6.19,
            "r2": 0.91,
        },
        figures=figures,
    )

    def run_filtered_ckp(*_args: Any, **_kwargs: Any) -> Any:
        assert active_frequencies == {"Q00": 5.1, "RQ00": 6.2}
        assert params.readout_amplitude["Q00"] == 0.2
        return result

    characterize = MagicMock(side_effect=run_filtered_ckp)
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "get_resonator_label", lambda _backend, _qid: "RQ00")
    monkeypatch.setattr(qubex.contrib, "filtered_ckp_experiment", characterize)
    return SimpleNamespace(
        task=task,
        backend=cast("Any", SimpleNamespace()),
        exp=exp,
        system_manager=system_manager,
        active_frequencies=active_frequencies,
        result=result,
        characterize=characterize,
    )


def test_run_scopes_inputs_and_disables_qubex_figure_side_effects(
    filtered_ckp: SimpleNamespace,
) -> None:
    run_result = filtered_ckp.task.run(filtered_ckp.backend, "0")

    assert run_result.r2 == {"0": 0.91}
    assert filtered_ckp.exp.params.readout_amplitude["Q00"] == 0.3
    assert filtered_ckp.active_frequencies == {}
    filtered_ckp.system_manager.modified_backend_settings.assert_not_called()
    kwargs = filtered_ckp.characterize.call_args.kwargs
    assert kwargs["target"] == "Q00"
    assert kwargs["plot"] is False
    assert kwargs["save_image"] is False
    assert kwargs["resonator_drive_amplitude"] == 0.1
    assert kwargs["qubit_detuning_range"].tolist() == [-0.02, 0.0, 0.02]
    assert kwargs["resonator_detuning_range"].tolist() == [-0.1, 0.0, 0.1]


def test_run_restores_overrides_when_qubex_fails(filtered_ckp: SimpleNamespace) -> None:
    filtered_ckp.characterize.side_effect = RuntimeError("CKP failed")

    with pytest.raises(RuntimeError, match="CKP failed"):
        filtered_ckp.task.run(filtered_ckp.backend, "0")

    assert filtered_ckp.exp.params.readout_amplitude["Q00"] == 0.3
    assert filtered_ckp.active_frequencies == {}
    filtered_ckp.system_manager.modified_backend_settings.assert_not_called()


def test_postprocess_converts_units_and_keeps_all_ckp_figures(
    filtered_ckp: SimpleNamespace,
) -> None:
    run_result = filtered_ckp.task.run(filtered_ckp.backend, "0")
    processed = filtered_ckp.task.postprocess(filtered_ckp.backend, "execution", run_result, "0")

    values = processed.output_parameters
    assert values["resonator_frequency"].value == 6.15
    assert values["readout_frequency"].value == 6.19
    assert values["purcell_filter_frequency"].value == 6.23
    assert values["resonator_purcell_filter_coupling"].value == 12.0
    assert values["purcell_filter_linewidth"].value == 45.0
    assert values["dispersive_shift"].value == -1.5
    assert values["critical_photon_number"].value == 22.0
    assert processed.figures == list(filtered_ckp.result.figures.values())
    assert processed.validation_error is None


def test_low_ckp_fit_r2_blocks_calibration_update_but_keeps_figures(
    filtered_ckp: SimpleNamespace,
) -> None:
    filtered_ckp.result.data["r2"] = 0.69

    run_result = filtered_ckp.task.run(filtered_ckp.backend, "0")
    processed = filtered_ckp.task.postprocess(filtered_ckp.backend, "execution", run_result, "0")

    assert processed.validation_error == "Filtered CKP fit R² must be greater than 0.7: 0.69"
    assert processed.figures == list(filtered_ckp.result.figures.values())


def test_threshold_ckp_fit_r2_blocks_calibration_update(
    filtered_ckp: SimpleNamespace,
) -> None:
    filtered_ckp.result.data["r2"] = filtered_ckp.task.r2_threshold

    run_result = filtered_ckp.task.run(filtered_ckp.backend, "0")
    processed = filtered_ckp.task.postprocess(filtered_ckp.backend, "execution", run_result, "0")

    assert processed.validation_error == "Filtered CKP fit R² must be greater than 0.7: 0.7"


def test_progress_accounts_for_optional_rough_search(filtered_ckp: SimpleNamespace) -> None:
    task = filtered_ckp.task
    assert task.get_progress_plan() == ProgressPlan(5, 18)

    task.run_parameters["max_rough_search_reductions"].value = 0
    task.run_parameters["max_rough_search_increases"].value = 0
    assert task.get_progress_plan() == ProgressPlan(5, 6)

    task.run_parameters["enable_rough_search"].value = False
    assert task.get_progress_plan() == ProgressPlan(4, 4)


def test_qubex_package_registers_filtered_ckp_task() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401
    from qdash.workflow.calibtasks.base import BaseTask

    assert BaseTask.registry["qubex"]["CharacterizeFilteredCKP"] is CharacterizeFilteredCKP
