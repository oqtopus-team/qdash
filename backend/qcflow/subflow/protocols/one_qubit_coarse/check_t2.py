import numpy as np
from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckT2(BaseTask):
    task_name: str = "CheckT2"
    output_parameters: dict = {"t2": {}}

    def __init__(
        self,
        time_range=np.logspace(
            np.log10(300),
            np.log10(100 * 1000),
            51,
        ),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ):
        self.input_parameters = {
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
        }

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        t2_result = exp.t2_experiment(
            exp.qubit_labels,
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
            save_image=True,
        )
        t2_values = {}
        for qubit in exp.qubit_labels:
            t2_values[qubit] = t2_result.data[qubit].t2 if qubit in t2_result.data else None
        self.output_parameters["t2"] = t2_values
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
        for qubit in t2_values:
            execution_manager.put_calibration_value(qubit, "t2", t2_values[qubit])
