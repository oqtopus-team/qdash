import numpy as np
from qcflow.subflow.qubex.manager import ExecutionManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckT1(BaseTask):
    task_name: str = "CheckT1"
    output_parameters: dict = {"t1": {}}

    def __init__(
        self,
        time_range=np.logspace(
            np.log10(100),
            np.log10(500 * 1000),
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
        t1_result = exp.t1_experiment(
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
            save_image=True,
        )
        t1_values = {}
        for qubit in exp.qubit_labels:
            t1_values[qubit] = t1_result.data[qubit].t1 if qubit in t1_result.data else None
        self.output_parameters["t1"] = t1_values
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
        for qubit in t1_values:
            execution_manager.put_calibration_value(qubit, "t1", t1_values[qubit])
