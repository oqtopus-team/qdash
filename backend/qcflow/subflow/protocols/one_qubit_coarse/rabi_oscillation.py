from typing import Any

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class RabiOscillation(BaseTask):
    task_name: str = "RabiOscillation"
    task_type: str = "qubit"

    def __init__(self):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        default_rabi_amplitudes = {label: 0.01 for label in exp.qubit_labels}
        exp.rabi_experiment(
            amplitudes=default_rabi_amplitudes,
            time_range=range(0, 201, 4),
            detuning=0.001,
            shots=300,
            interval=50_000,
        )
        exp.save_defaults()
