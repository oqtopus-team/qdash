from typing import Any, ClassVar

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class ZX90InterleavedRandomizedBenchmarking(BaseTask):
    """Task to perform ZX90 interleaved randomized benchmarking."""

    task_name: str = "ZX90InterleavedRandomizedBenchmarking"
    task_type: str = "coupling"
    output_parameters: ClassVar[list[str]] = ["zx90_gate_fidelity"]

    def __init__(
        self,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
        n_cliffords_range=np.arange(0, 1001, 100),
        n_trials=30,
    ) -> None:
        self.input_parameters = {
            "n_cliffords_range": n_cliffords_range,
            "n_trials": n_trials,
            "shots": shots,
            "interval": interval,
        }

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, label: str) -> None:
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

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, label: str
    ) -> None:
        output_param = {
            "zx90_gate_fidelity": Data(
                value=result["mean"][label], execution_id=task_manager.execution_id
            ),
        }
        task_manager.put_output_parameters(
            self.task_name,
            output_param,
            self.task_type,
            qid=convert_qid(label),
        )
        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
        for label in exp.qubit_labels:
            self._preprocess(exp, task_manager, label)
            result = exp.randomized_benchmarking(
                target=label,
                n_cliffords_range=self.input_parameters["n_cliffords_range"],
                n_trials=self.input_parameters["n_trials"],
                x90=exp.drag_hpi_pulse[label],
                save_image=True,
                shots=self.input_parameters["shots"],
                interval=self.input_parameters["interval"],
            )
            exp.calib_note.save()
            self._postprocess(exp, task_manager, result, label)
