from typing import Any

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class RandomizedBenchmarking(BaseTask):
    task_name: str = "RandomizedBenchmarking"
    task_type: str = "qubit"
    output_parameters: dict = {"average_gate_fidelity": {}}

    def __init__(
        self,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
        n_cliffords_range=np.arange(0, 1001, 100),
        n_trials=30,
    ):
        self.input_parameters = {
            "n_cliffords_range": n_cliffords_range,
            "n_trials": n_trials,
            "shots": shots,
            "interval": interval,
        }

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        for label in exp.qubit_labels:
            input_param = {
                "n_cliffords_range": self.input_parameters["n_cliffords_range"],
                "n_trials": self.input_parameters["n_trials"],
                "shots": self.input_parameters["shots"],
                "interval": self.input_parameters["interval"],
            }
            task_manager.put_input_parameters(
                self.task_name,
                input_param,
                self.task_type,
                qid=convert_qid(label),
            )

        task_manager.save()

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any, label: str):
        output_param = {
            "average_gate_fidelity": result["avg_gate_fidelity"],
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
            parameter_name="average_gate_fidelity",
            data=Data(value=result["avg_gate_fidelity"]),
        )
        task_manager.save_figure(
            task_name=self.task_name,
            task_type=self.task_type,
            figure=result["fig"],
            qid=convert_qid(label),
        )

    def execute(self, exp: Experiment, task_manager: TaskManager):
        self._preprocess(exp, task_manager)
        for label in exp.qubit_labels:
            result = exp.randomized_benchmarking(
                target=label,
                n_cliffords_range=self.input_parameters["n_cliffords_range"],
                n_trials=self.input_parameters["n_trials"],
                x90=exp.drag_hpi_pulse[label],
                save_image=True,
                shots=self.input_parameters["shots"],
                interval=self.input_parameters["interval"],
            )
            self._postprocess(exp, task_manager, result, label)
        exp.calib_note.save()
