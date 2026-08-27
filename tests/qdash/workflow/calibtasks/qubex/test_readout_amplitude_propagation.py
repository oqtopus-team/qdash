import pytest

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.cw.check_control_amplitude import CheckControlAmplitude
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import CheckQubitSpectroscopy
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_chevron import CheckChevron
from qdash.workflow.service.tasks import BRINGUP_TASKS


def test_bringup_tasks_prefer_loaded_readout_amplitude() -> None:
    for task_cls in (
        CheckQubitSpectroscopy,
        CheckControlAmplitude,
        CheckChevron,
    ):
        task = task_cls()
        task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.017, unit="a.u.")

        assert task._get_readout_amplitude_value() == 0.017


def test_readout_amplitude_requires_resolved_calibration_input() -> None:
    task = CheckQubitSpectroscopy()

    with pytest.raises(ValueError, match="readout_amplitude input parameter is required"):
        task._get_readout_amplitude_value()


def test_bringup_tasks_declare_readout_amplitude_as_calibration_input() -> None:
    for task_cls in (
        CheckQubitSpectroscopy,
        CheckControlAmplitude,
        CheckChevron,
    ):
        assert "readout_amplitude" in task_cls.input_spec


def test_cw_tasks_do_not_declare_readout_amplitude_as_run_parameter() -> None:
    for task_cls in (CheckQubitSpectroscopy, CheckControlAmplitude):
        assert "readout_amplitude" not in task_cls.run_spec


def test_bringup_uses_adaptive_check_chevron_before_fine_refinement() -> None:
    assert "CheckChevron" in BRINGUP_TASKS
    assert "CheckCoarseChevron" not in BRINGUP_TASKS
    assert "Configure" not in BRINGUP_TASKS
    assert "CheckRabi" not in BRINGUP_TASKS
    assert "CheckControlAmplitude" in BRINGUP_TASKS
    assert BRINGUP_TASKS.index("CheckControlAmplitude") > BRINGUP_TASKS.index(
        "CheckQubitSpectroscopy"
    )
    assert BRINGUP_TASKS.index("CheckChevron") > BRINGUP_TASKS.index("CheckControlAmplitude")
    assert BRINGUP_TASKS.index("CheckChevron") > BRINGUP_TASKS.index("CheckQubitSpectroscopy")
