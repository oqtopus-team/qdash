from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.qubex.cw.check_control_amplitude import CheckControlAmplitude
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import CheckQubitSpectroscopy
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_chevron import CheckChevron
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_coarse_chevron import (
    CheckCoarseChevron,
)
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_fine_chevron import (
    CheckFineChevron,
)
from qdash.workflow.service.tasks import BRINGUP_TASKS, EXPERIMENTAL_SIMULTANEOUS_BRINGUP_TASKS


def test_bringup_tasks_prefer_loaded_readout_amplitude() -> None:
    for task_cls in (
        CheckQubitSpectroscopy,
        CheckControlAmplitude,
        CheckChevron,
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
        CheckChevron,
        CheckCoarseChevron,
        CheckFineChevron,
    ):
        assert "readout_amplitude" in task_cls.input_parameters


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


def test_experimental_simultaneous_bringup_runs_regular_followup_tasks() -> None:
    assert EXPERIMENTAL_SIMULTANEOUS_BRINGUP_TASKS == [
        "CheckResonatorSpectroscopy",
        "CheckSimultaneousQubitSpectroscopy",
        "CheckControlAmplitude",
        "CheckChevron",
    ]
