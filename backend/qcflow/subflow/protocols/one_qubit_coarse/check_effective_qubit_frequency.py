from typing import Any, ClassVar

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_label, convert_qid
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckEffectiveQubitFrequency(BaseTask):
    """Task to check the effective qubit frequency."""

    task_name: str = "CheckEffectiveQubitFrequency"
    task_type: str = "qubit"
    output_parameters: ClassVar[list[str]] = [
        "effective_qubit_frequency",
        "effective_qubit_frequency_0",
        "effective_qubit_frequency_1",
    ]

    def __init__(
        self,
        detuning=0.001,
        time_range=np.arange(0, 20001, 100),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ) -> None:
        self.input_parameters = {
            "detuning": detuning,
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
        }

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
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
            qid=qid,
        )
        task_manager.save()

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, qid: str
    ) -> None:
        label = convert_label(qid)
        output_param = {
            "effective_qubit_frequency": Data(
                value=result["effective_freq"][label],
                unit="GHz",
                execution_id=task_manager.execution_id,
            ),
            "effective_qubit_frequency_0": Data(
                value=result["result_0"].data[label].bare_freq,
                unit="GHz",
                execution_id=task_manager.execution_id,
            ),
            "effective_qubit_frequency_1": Data(
                value=result["result_1"].data[label].bare_freq,
                unit="GHz",
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
            figure=result["result_0"].data[label].fit()["fig"],
            qid=qid,
        )
        task_manager.save_figure(
            task_name=self.task_name,
            task_type=self.task_type,
            figure=result["result_1"].data[label].fit()["fig"],
            qid=qid,
        )

        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        self._preprocess(exp, task_manager, qid=qid)
        labels = [convert_label(qid)]
        result = exp.obtain_effective_control_frequency(
            targets=labels,
            time_range=self.input_parameters["time_range"],
            detuning=self.input_parameters["detuning"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save()
        self._postprocess(exp, task_manager, result, qid=qid)
