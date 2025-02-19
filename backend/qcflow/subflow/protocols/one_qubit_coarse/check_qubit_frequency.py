from typing import Any

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckQubitFrequency(BaseTask):
    task_name: str = "CheckQubitFrequency"
    task_type: str = "qubit"
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
            "qubit_frequency": 0.0,
            "control_amplitude": 0.0,
        }

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        for label in exp.qubit_labels:
            input_param = {
                "detuning_range": self.input_parameters["detuning_range"],
                "time_range": self.input_parameters["time_range"],
                "shots": self.input_parameters["shots"],
                "interval": self.input_parameters["interval"],
                "qubit_frequency": exp.targets[label].frequency,
                "control_amplitude": exp.params.control_amplitude[label],
            }
            task_manager.put_input_parameters(
                self.task_name,
                input_param,
                self.task_type,
                qid=convert_qid(label),
            )
        task_manager.save()

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any):
        for label in exp.qubit_labels:
            output_param = {
                "qubit_frequency": result[label],
            }
            task_manager.put_output_parameters(
                self.task_name,
                output_param,
                self.task_type,
                qid=convert_qid(label),
            )
            task_manager.put_calib_data(
                qid=convert_qid(label),
                task_type=self.task_type,
                parameter_name="qubit_frequency",
                data=Data(value=result[label], unit="GHz"),
            )
        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager):
        self._preprocess(exp, task_manager)
        result = exp.calibrate_control_frequency(
            exp.qubit_labels,
            detuning_range=self.input_parameters["detuning_range"],
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save(file_path=task_manager.calib_dir)
        self._postprocess(exp, task_manager, result)
