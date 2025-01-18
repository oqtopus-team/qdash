import numpy as np
from qcflow.subflow.qubex.manager import ExecutionManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment


class CheckT1(BaseTask):
    task_name: str = "CheckT1"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
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
        execution_manager.put_output_parameter(self.task_name, "t1", t1_values)
