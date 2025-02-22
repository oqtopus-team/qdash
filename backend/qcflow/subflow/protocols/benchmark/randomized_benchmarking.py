from typing import Any, ClassVar

import numpy as np
from qcflow.subflow.protocols.base import BaseTask, OutputParameter
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_label, convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class RandomizedBenchmarking(BaseTask):
    """Task to perform randomized benchmarking."""

    task_name: str = "RandomizedBenchmarking"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "average_gate_fidelity": OutputParameter(
            unit="",
            description="Average gate fidelity",
        ),
    }

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

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
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
            qid=qid,
        )

        task_manager.save()

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, qid: str
    ) -> None:
        op = self.output_parameters
        output_param = {
            "average_gate_fidelity": Data(
                value=result["avg_gate_fidelity"],
                unit=op["average_gate_fidelity"].unit,
                description=op["average_gate_fidelity"].description,
                execution_id=task_manager.execution_id,
            ),
        }
        task_manager.put_output_parameters(
            self.task_name,
            output_param,
            self.task_type,
            qid=qid,
        )
        task_manager.save_figure(
            task_name=self.task_name,
            task_type=self.task_type,
            figure=result["fig"],
            qid=qid,
        )

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        self._preprocess(exp, task_manager, qid=qid)
        label = convert_label(qid)
        result = exp.randomized_benchmarking(
            target=label,
            n_cliffords_range=self.input_parameters["n_cliffords_range"],
            n_trials=self.input_parameters["n_trials"],
            x90=exp.drag_hpi_pulse[label],
            save_image=True,
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        self._postprocess(exp, task_manager, result, qid=qid)
        exp.calib_note.save()
