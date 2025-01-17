from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CreateHPIPulse(BaseTask):
    task_name = "CreateHPIPulse"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        hpi_result = exp.calibrate_hpi_pulse(
            exp.qubit_labels,
            n_rotations=1,
        )
        exp.save_defaults()
        hpi_amplitudes = {}
        for qubit in exp.qubit_labels:
            hpi_amplitudes[qubit] = (
                hpi_result.data[qubit].calib_value if qubit in hpi_result.data else None
            )
        task_manager.put_output_parameter(task_name, "hpi_amplitude", hpi_amplitudes)
