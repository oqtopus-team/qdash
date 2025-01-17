from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CreatePIPulse(BaseTask):
    task_name = "CreatePIPulse"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        pi_result = exp.calibrate_pi_pulse(
            exp.qubit_labels,
            n_rotations=1,
        )
        exp.save_defaults()
        pi_amplitudes = {}
        for qubit in exp.qubit_labels:
            pi_amplitudes[qubit] = (
                pi_result.data[qubit].calib_value if qubit in pi_result.data else None
            )
        task_manager.put_output_parameter(task_name, "pi_amplitude", pi_amplitudes)
