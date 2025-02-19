from typing import Any

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckEffectiveQubitFrequency(BaseTask):
    task_name: str = "CheckEffectiveQubitFrequency"
    task_type: str = "qubit"
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

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        for qid in exp.qubit_labels:
            input_param = {
                "detuning": self.input_parameters["detuning"],
                "time_range": self.input_parameters["time_range"],
                "shots": self.input_parameters["shots"],
                "interval": self.input_parameters["interval"],
            }
            task_manager.put_input_parameters(
                self.task_name,
                input_param,
                self.task_type,
                qid=convert_qid(qid),
            )
        task_manager.save()

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any):
        for label in exp.qubit_labels:
            output_param = {
                "effective_qubit_frequency": result["effective_freq"][label],
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
                parameter_name="effective_qubit_frequency",
                data=Data(value=result["effective_freq"][label]),
            )
            task_manager.put_calib_data(
                qid=convert_qid(label),
                task_type=self.task_type,
                parameter_name="effective_qubit_frequency_0",
                data=Data(value=result["result_0"].data[label].bare_freq),
            )
            task_manager.put_calib_data(
                qid=convert_qid(label),
                task_type=self.task_type,
                parameter_name="effective_qubit_frequency_1",
                data=Data(value=result["result_1"].data[label].bare_freq),
            )
            task_manager.save_figure(
                task_name=self.task_name,
                task_type=self.task_type,
                figure=result["result_0"].data[label].fit()["fig"],
                qid=convert_qid(label),
            )
            task_manager.save_figure(
                task_name=self.task_name,
                task_type=self.task_type,
                figure=result["result_1"].data[label].fit()["fig"],
                qid=convert_qid(label),
            )

        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager):
        self._preprocess(exp, task_manager)
        result = exp.obtain_effective_control_frequency(
            exp.qubit_labels,
            time_range=self.input_parameters["time_range"],
            detuning=self.input_parameters["detuning"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save()
        self._postprocess(exp, task_manager, result)
