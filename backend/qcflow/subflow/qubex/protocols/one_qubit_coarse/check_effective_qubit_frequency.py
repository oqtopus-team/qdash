import numpy as np
from qcflow.subflow.qubex.manager import TaskManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment


class CheckEffectiveQubitFrequency(BaseTask):
    task_name: str = "CheckEffectiveQubitFrequency"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        effective_control_frequency_result = exp.obtain_effective_control_frequency(
            exp.qubit_labels,
            time_range=np.arange(0, 20001, 100),
            detuning=0.001,
        )
        task_manager.put_output_parameter(
            self.task_name,
            "effective_qubit_frequency",
            effective_control_frequency_result["effective_freq"],
        )
