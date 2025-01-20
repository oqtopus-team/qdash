import numpy as np
from qcflow.subflow.qubex.manager import ExecutionManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckEffectiveQubitFrequency(BaseTask):
    task_name: str = "CheckEffectiveQubitFrequency"
    output_parameters: dict = {"effective_qubit_frequency": {}}

    def __init__(
        self,
        detuning=0.001,
        time_range=np.arange(0, 20001, 100),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ):
        self.input_parameters = {
            "detuning": detuning,
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
        }

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        effective_control_frequency_result = exp.obtain_effective_control_frequency(
            exp.qubit_labels,
            time_range=self.input_parameters["time_range"],
            detuning=self.input_parameters["detuning"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        self.output_parameters["effective_qubit_frequency"] = effective_control_frequency_result[
            "effective_freq"
        ]
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
