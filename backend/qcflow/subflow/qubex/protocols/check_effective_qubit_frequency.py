import numpy as np
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckEffectiveQubitFrequency(BaseTask):
    task_name = "CheckEffectiveQubitFrequency"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        effective_control_frequency_result = exp.obtain_effective_control_frequency(
            exp.qubit_labels,
            time_range=np.arange(0, 20001, 100),
            detuning=0.001,
        )
        task_manager.put_output_parameter(
            task_name,
            "effective_qubit_frequency",
            effective_control_frequency_result["effective_freq"],
        )
