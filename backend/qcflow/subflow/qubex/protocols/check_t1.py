import numpy as np
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckT1(BaseTask):
    task_name = "CheckT1"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        t1_result = exp.t1_experiment(
            time_range=np.logspace(
                np.log10(100),
                np.log10(500 * 1000),
                51,
            ),
            save_image=True,
        )
        t1_values = {}
        for qubit in exp.qubit_labels:
            t1_values[qubit] = t1_result.data[qubit].t1 if qubit in t1_result.data else None
        task_manager.put_output_parameter(task_name, "t1", t1_values)
