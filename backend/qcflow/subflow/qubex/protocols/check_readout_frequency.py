import numpy as np
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckReadoutFrequency(BaseTask):
    task_name = "CheckReadoutFrequency"

    def __init__(self):
        self.detuning_range = np.linspace(-0.01, 0.01, 21)
        self.time_range = range(0, 101, 4)

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        readout_frequency = exp.calibrate_readout_frequency(
            exp.qubit_labels,
            detuning_range=self.detuning_range,
            time_range=self.time_range,
        )
        exp.save_defaults()
        task_manager.put_output_parameter(task_name, "readout_frequency", readout_frequency)
