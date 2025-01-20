import numpy as np
from qcflow.subflow.qubex.manager import ExecutionManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckQubitFrequency(BaseTask):
    task_name: str = "CheckQubitFrequency"
    output_parameters: dict = {"qubit_frequency": {}}

    def __init__(
        self,
        detuning_range=np.linspace(-0.01, 0.01, 21),
        time_range=range(0, 101, 4),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ):
        self.input_parameters: dict = {
            "detuning_range": detuning_range,
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": {},
            "control_amplitude": {},
        }

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        self.input_parameters["qubit_frequency"] = {
            target: exp.targets[target].frequency for target in exp.qubit_labels
        }
        self.input_parameters["control_amplitude"] = {
            target: exp.params.control_amplitude[target] for target in exp.qubit_labels
        }
        execution_manager.put_input_parameters(self.task_name, self.input_parameters)
        qubit_frequency = exp.calibrate_control_frequency(
            exp.qubit_labels,
            detuning_range=self.input_parameters["detuning_range"],
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.save_defaults()
        self.output_parameters["qubit_frequency"] = qubit_frequency
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
