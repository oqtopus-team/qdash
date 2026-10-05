import pytest

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.cw.check_control_amplitude import CheckControlAmplitude
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import CheckQubitSpectroscopy
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_adaptive_chevron import (
    CheckAdaptiveChevron,
)
from qdash.workflow.service.tasks import BRINGUP_TASKS


def test_bringup_tasks_prefer_loaded_readout_amplitude() -> None:
    """Verify bring-up tasks use the resolved readout-amplitude calibration input."""
    for task_cls in (
        CheckQubitSpectroscopy,
        CheckControlAmplitude,
        CheckAdaptiveChevron,
    ):
        task = task_cls()
        task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.017, unit="a.u.")

        assert task._get_readout_amplitude_value() == 0.017


def test_readout_amplitude_requires_resolved_calibration_input() -> None:
    """Verify a missing readout-amplitude calibration input fails explicitly."""
    task = CheckQubitSpectroscopy()

    with pytest.raises(ValueError, match="readout_amplitude input parameter is required"):
        task._get_readout_amplitude_value()


def test_bringup_tasks_declare_readout_amplitude_as_calibration_input() -> None:
    """Verify bring-up tasks declare readout amplitude as a calibration input."""
    for task_cls in (
        CheckQubitSpectroscopy,
        CheckControlAmplitude,
        CheckAdaptiveChevron,
    ):
        assert "readout_amplitude" in task_cls.input_spec


def test_cw_tasks_do_not_declare_readout_amplitude_as_run_parameter() -> None:
    """Verify CW tasks do not duplicate readout amplitude in their run parameters."""
    for task_cls in (CheckQubitSpectroscopy, CheckControlAmplitude):
        assert "readout_amplitude" not in task_cls.run_spec


def test_bringup_uses_adaptive_chevron_after_coarse_calibration() -> None:
    """Verify bring-up orders adaptive chevron after CW calibration tasks."""
    assert "CheckAdaptiveChevron" in BRINGUP_TASKS
    assert "CheckChevron" not in BRINGUP_TASKS
    assert "CheckCoarseChevron" not in BRINGUP_TASKS
    assert "Configure" not in BRINGUP_TASKS
    assert "CheckRabi" not in BRINGUP_TASKS
    assert "CheckControlAmplitude" in BRINGUP_TASKS
    assert BRINGUP_TASKS.index("CheckControlAmplitude") > BRINGUP_TASKS.index(
        "CheckQubitSpectroscopy"
    )
    assert BRINGUP_TASKS.index("CheckAdaptiveChevron") > BRINGUP_TASKS.index(
        "CheckControlAmplitude"
    )
    assert BRINGUP_TASKS.index("CheckAdaptiveChevron") > BRINGUP_TASKS.index(
        "CheckQubitSpectroscopy"
    )
