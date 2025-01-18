import numpy as np
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckT2(BaseTask):
    task_name: str = "CheckT2"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        t2_result = exp.t2_experiment(
            exp.qubit_labels,
            time_range=np.logspace(
                np.log10(300),
                np.log10(100 * 1000),
                51,
            ),
            save_image=True,
        )
        t2_values = {}
        for qubit in exp.qubit_labels:
            t2_values[qubit] = t2_result.data[qubit].t2 if qubit in t2_result.data else None
        task_manager.put_output_parameter(self.task_name, "t2", t2_values)
