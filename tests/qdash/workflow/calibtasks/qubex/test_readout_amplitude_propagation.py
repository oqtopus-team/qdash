from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.qubex.cw.check_control_amplitude import CheckControlAmplitude
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import CheckQubitSpectroscopy
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_coarse_chevron import (
    CheckCoarseChevron,
)
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_fine_chevron import (
    CheckFineChevron,
)


def test_bringup_tasks_prefer_loaded_readout_amplitude() -> None:
    for task_cls in (
        CheckQubitSpectroscopy,
        CheckControlAmplitude,
        CheckCoarseChevron,
        CheckFineChevron,
    ):
        task = task_cls()
        task.input_parameters["readout_amplitude"] = ParameterModel(value=0.017, unit="a.u.")

        assert task._get_readout_amplitude_value() == 0.017


def test_readout_amplitude_falls_back_to_run_parameter_default() -> None:
    task = CheckQubitSpectroscopy()

    assert task._get_readout_amplitude_value() == 0.04


def test_bringup_tasks_declare_readout_amplitude_as_calibration_input() -> None:
    for task_cls in (
        CheckQubitSpectroscopy,
        CheckControlAmplitude,
        CheckCoarseChevron,
        CheckFineChevron,
    ):
        assert "readout_amplitude" in task_cls.input_parameters
