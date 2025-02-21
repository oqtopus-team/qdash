from typing import Any, ClassVar

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_label, convert_qid
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckT2Echo(BaseTask):
    """Task to check the T2 echo time."""

    task_name: str = "CheckT2Echo"
    task_type: str = "qubit"
    output_parameters: ClassVar[list[str]] = ["t2_echo"]

    def __init__(
        self,
        time_range=np.logspace(
            np.log10(300),
            np.log10(100 * 1000),
            51,
        ),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ) -> None:
        self.input_parameters = {
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
        }

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        input_param = {
            "time_range": self.input_parameters["time_range"],
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
        label = convert_label(qid)
        output_param = {
            "t2_echo": Data(value=result.data[label].t2, unit="ns"),
        }
        task_manager.put_output_parameters(
            self.task_name,
            output_param,
            self.task_type,
            qid=qid,
        )
        task_manager.put_calib_data(
            qid=qid,
            task_type=self.task_type,
            parameter_name="t2_echo",
            data=Data(value=result.data[label].t2, unit="ns"),
        )
        task_manager.save_figure(
            task_name=self.task_name,
            task_type=self.task_type,
            figure=result.data[label].fit()["fig"],
            qid=qid,
        )
        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        self._preprocess(exp, task_manager, qid=qid)
        labels = [convert_label(qid)]
        result = exp.t2_experiment(
            labels,
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
            save_image=True,
        )
        self._postprocess(exp, task_manager, result, qid=qid)
